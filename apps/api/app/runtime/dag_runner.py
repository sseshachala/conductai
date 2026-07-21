"""
DAG runner — topological execution loop and block dispatch.

Dependency order: runtime → tool_engine → dag_runner → executor
"""
from __future__ import annotations

import json
import re
import time
import uuid
from collections import defaultdict, deque
from datetime import timezone
from typing import Any

import structlog

from app.core.config import settings
from app.core.credentials import CredentialStore  # re-exported for backward compat
from app.runtime.runtime import _emit, _now, _agent_config, _resolve_refs

log = structlog.get_logger(__name__)


# ── flow-control exceptions ───────────────────────────────────────────────────
from app.runtime.exceptions import ApprovalRequired, ClarificationRequired  # noqa: F401


def _classify_failure(exc: Exception, block_id: str | None = None) -> dict[str, Any]:
    """Normalize runtime failures into a structured, user-actionable summary."""
    msg = str(exc)

    code = "EXECUTION_ERROR"
    category = "runtime"
    stop_reason = "exception"
    next_action = "Inspect the failed block output and rerun after fixing the underlying error."

    if isinstance(exc, ClarificationRequired):
        code = "CLARIFICATION_REQUIRED"
        category = "input_contract"
        stop_reason = "awaiting_clarification"
        next_action = "Answer the clarification question via POST /runs/{run_id}/clarify to resume the run."
    elif isinstance(exc, PermissionError):
        code = "EGRESS_POLICY_BLOCKED"
        category = "governance"
        stop_reason = "policy_block"
        next_action = "Update allowed_hosts for this environment or remove the blocked outbound call."
    elif "[ConductGuard] Blocked by policy" in msg:
        # Guard policy fired — this is a governance decision, not a crash.
        # Surface it as such so the UI shows a clean "blocked" state and
        # the user knows where to go to fix it.
        code = "GUARD_POLICY_BLOCKED"
        category = "governance"
        stop_reason = "policy_block"
        # Pull the rule_id out of the message for a more actionable hint
        m = re.search(r"policy '([^']+)'", msg)
        rule_id = m.group(1) if m else None
        next_action = (
            (f"Guard rule '{rule_id}' blocked this step. " if rule_id else "Guard blocked this step. ") +
            "Disable Guard for this workflow in Settings → ConductGuard, "
            "or change the rule action at /guard/policies."
        )
    elif isinstance(exc, RuntimeError) and "Turn budget exhausted" in msg:
        code = "RETRY_BUDGET_EXHAUSTED"
        category = "reliability"
        stop_reason = "max_turns_reached"
        next_action = "Tighten the task scope or increase the run turn budget for this workflow."
    elif isinstance(exc, RuntimeError) and "Cost budget exhausted" in msg:
        code = "COST_BUDGET_EXHAUSTED"
        category = "reliability"
        stop_reason = "max_cost_reached"
        next_action = "Reduce task scope or raise the cost cap for this workflow run."
    elif isinstance(exc, ValueError) and msg.startswith("NEEDS_CLARIFICATION:"):
        code = "INSUFFICIENT_INPUT_CONTEXT"
        category = "input_contract"
        stop_reason = "missing_context"
        next_action = "Provide clearer trigger context or required inputs before starting the run."
    elif "Approval rejected" in msg:
        code = "APPROVAL_REJECTED"
        category = "approval"
        stop_reason = "human_rejected"
        next_action = "Review rejection feedback, update the plan, and rerun for approval."
    elif msg == "Connection error." or "APIConnectionError" in type(exc).__name__:
        # Unwrap the real cause (httpx error) for a more useful message.
        cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
        cause_msg = str(cause) if cause else ""
        code = "LLM_CONNECTION_ERROR"
        category = "connectivity"
        stop_reason = "exception"
        msg = f"LLM connection failed — {cause_msg}" if cause_msg else "LLM connection failed (check proxy URL and agent token)"
        next_action = "Check that the Conduct proxy URL is reachable and CONDUCT_AGENT_TOKEN is set in this environment."

    return {
        "code": code,
        "category": category,
        "stop_reason": stop_reason,
        "message": msg,
        "block_id": block_id,
        "next_action": next_action,
    }

_STATE_CHECKPOINT_TTL = 604800  # 7 days — Redis LLM-cache TTL (unchanged)

# Module-level Redis connection pool — used as optional read cache only.
import redis as _redis_mod
import json as _json_mod
_redis_pool = _redis_mod.ConnectionPool.from_url(settings.redis_url, decode_responses=True)


def _redis_client() -> "_redis_mod.Redis":
    return _redis_mod.Redis(connection_pool=_redis_pool)


# ── state checkpointing ───────────────────────────────────────────────────────

def _checkpoint_state(
    run_id: str | None,
    state: dict,
    db=None,
    block_id: str | None = None,
    attempt_id: str | None = None,
    partial: bool = False,
    resume_from_turn: int = 0,
) -> None:
    """Atomic DB upsert for per-block checkpoint.

    Writes to run_block_states via INSERT ... ON CONFLICT DO UPDATE so the
    operation is a single round-trip with no crash window between completion
    and persistence.

    Also updates runs.last_heartbeat_time so the reaper does not kill
    long-running agentic blocks mid-execution.

    Redis write is best-effort: used only as a warm read cache on resume.
    A Redis failure never raises — the DB row is the source of truth.
    """
    if not run_id or not db or not block_id:
        return

    from datetime import datetime as _dt
    _completed_at = None if partial else _dt.now(timezone.utc).isoformat()

    try:
        import sqlalchemy as _sa

        # Build the upsert using raw SQL for portability with both sync and
        # greenlet-threaded SQLAlchemy sessions used in the worker.
        _upsert_sql = _sa.text("""
            INSERT INTO run_block_states
                (run_id, block_id, attempt_id, output, partial, resume_from_turn, completed_at, created_at)
            VALUES
                (:run_id, :block_id, :attempt_id, CAST(:output AS jsonb), :partial, :resume_from_turn, CAST(:completed_at AS timestamptz), now())
            ON CONFLICT (run_id, block_id) DO UPDATE SET
                attempt_id       = EXCLUDED.attempt_id,
                output           = EXCLUDED.output,
                partial          = EXCLUDED.partial,
                resume_from_turn = EXCLUDED.resume_from_turn,
                completed_at     = EXCLUDED.completed_at
        """)

        # For partial checkpoints preserve last known output so a mid-block
        # crash doesn't wipe what the block has produced so far.
        _output_json = _json_mod.dumps(
            state.get(block_id, {}),
            default=str,
        )

        db.execute(_upsert_sql, {
            "run_id":           str(run_id),
            "block_id":         block_id,
            "attempt_id":       str(attempt_id or uuid.uuid4()),
            "output":           _output_json,
            "partial":          partial,
            "resume_from_turn": resume_from_turn,
            "completed_at":     _completed_at,
        })
        db.commit()

    except Exception as _e:
        log.warning("dag.checkpoint_failed", run_id=run_id, block_id=block_id, error=str(_e))
        try:
            db.rollback()
        except Exception:
            pass
        return

    # Heartbeat — separate transaction so a lock contention on runs table
    # never rolls back the already-committed run_block_states upsert.
    try:
        import sqlalchemy as _sa
        db.execute(
            _sa.text("UPDATE runs SET last_heartbeat_time = now() WHERE id = :run_id"),
            {"run_id": str(run_id)},
        )
        db.commit()
    except Exception as _he:
        log.warning("dag.heartbeat_failed", run_id=run_id, error=str(_he))
        try:
            db.rollback()
        except Exception:
            pass

    # Best-effort Redis write — warm cache only, never the source of truth
    try:
        _redis_client().setex(
            f"run_state:{run_id}",
            _STATE_CHECKPOINT_TTL,
            _json_mod.dumps(state, default=str),
        )
    except Exception:
        pass  # Redis failure is non-fatal


def _load_checkpoint(run_id: str | None, db=None) -> tuple[dict, list]:
    """Load per-block checkpoint rows from DB.

    Returns (completed_outputs, block_state_rows) where:
    - completed_outputs: {block_id: output_dict} for rows with partial=False
    - block_state_rows: all RunBlockState rows for this run (both partial and complete)

    Falls back to Redis if db is None or query fails (legacy runs keep working).
    """
    if not run_id:
        return {}, []

    if db is not None:
        try:
            import sqlalchemy as _sa
            rows = db.execute(
                _sa.text("SELECT block_id, attempt_id, output, partial, resume_from_turn FROM run_block_states WHERE run_id = :run_id"),
                {"run_id": str(run_id)},
            ).fetchall()

            completed_outputs: dict = {}
            row_objects: list = []

            for row in rows:
                # Wrap raw Row into a simple namespace for attribute access
                class _Row:
                    pass
                r = _Row()
                r.block_id        = row[0]
                r.attempt_id      = str(row[1])
                r.output          = row[2] if isinstance(row[2], dict) else (_json_mod.loads(row[2]) if row[2] else {})
                r.partial         = row[3]
                r.resume_from_turn = row[4]
                row_objects.append(r)
                if not r.partial:
                    completed_outputs[r.block_id] = r.output

            return completed_outputs, row_objects
        except Exception as _e:
            log.warning("dag.load_checkpoint_failed", run_id=run_id, error=str(_e))

    # Redis fallback — for legacy runs that have no DB rows yet
    try:
        raw = _redis_client().get(f"run_state:{run_id}")
        if raw:
            legacy_state = _json_mod.loads(raw)
            return legacy_state, []
    except Exception:
        pass

    return {}, []


# ── graph utilities ───────────────────────────────────────────────────────────

def _topological_sort(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """Kahn's algorithm — returns nodes in execution order."""
    id_to_node = {n["id"]: n for n in nodes}
    in_degree: dict[str, int] = defaultdict(int)
    adjacency: dict[str, list[str]] = defaultdict(list)

    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        adjacency[src].append(tgt)
        in_degree[tgt] += 1

    queue = deque(n["id"] for n in nodes if in_degree[n["id"]] == 0)
    order: list[dict] = []

    while queue:
        nid = queue.popleft()
        order.append(id_to_node[nid])
        for neighbor in adjacency[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if len(order) != len(nodes):
        cycle_ids = [n["id"] for n in nodes if n["id"] not in {o["id"] for o in order}]
        raise RuntimeError(f"Workflow contains a cycle involving blocks: {cycle_ids}")
    return order


def _find_skipped_blocks(nodes: list[dict], edges: list[dict], logic_routes: dict[str, str]) -> set[str]:
    """
    Given resolved logic block routes {block_id: 'pass'|'fail'}, return the set
    of block IDs that are unreachable via live edges.

    Uses forward reachability: start from entry blocks (no incoming edges),
    follow only live edges (excluding non-taken logic branches), and mark
    everything not reached as skipped.

    This correctly handles convergent paths where a block is both the
    non-taken target of a logic block AND reachable via a live edge from
    another block (e.g. record_outcome after create_tracking_issue).
    """
    if not logic_routes:
        return set()

    all_node_ids = {n["id"] for n in nodes}

    # Build set of dead (source, target) pairs — non-taken logic branch edges
    dead_edges: set[tuple[str, str]] = set()
    for edge in edges:
        src = edge.get("source", "")
        if src in logic_routes:
            handle = edge.get("sourceHandle") or "pass"
            if handle != logic_routes[src]:
                dead_edges.add((src, edge["target"]))

    # Entry blocks: no incoming edges at all
    has_incoming = {e["target"] for e in edges}
    reachable: set[str] = all_node_ids - has_incoming

    # Forward BFS following only live edges
    changed = True
    while changed:
        changed = False
        for edge in edges:
            src = edge.get("source", "")
            tgt = edge.get("target", "")
            if (src, tgt) in dead_edges:
                continue
            if src in reachable and tgt not in reachable:
                reachable.add(tgt)
                changed = True

    return all_node_ids - reachable


# ── retry wrapper ─────────────────────────────────────────────────────────────

def _with_retry(execute_fn, retry_cfg: dict, *args, **kwargs):
    """
    Wrap execute_fn with per-block retry logic.

    retry_cfg keys:
      max      — int, total attempts (default 1 = no retry)
      backoff  — "fixed" | "exponential"  (default "fixed")
      on       — list of error categories to retry:
                 "tool_error" | "timeout" | "llm_parse_error"
                 (default ["tool_error", "timeout"])
    """
    max_attempts = int(retry_cfg.get("max", 1)) if isinstance(retry_cfg, dict) else int(getattr(retry_cfg, "max", 1))
    backoff = retry_cfg.get("backoff", "fixed") if isinstance(retry_cfg, dict) else getattr(retry_cfg, "backoff", "fixed")
    _on_raw = retry_cfg.get("on", ["tool_error", "timeout"]) if isinstance(retry_cfg, dict) else getattr(retry_cfg, "on", ["tool_error", "timeout"])
    on_categories = set(_on_raw)

    # Hard floor — must have at least one attempt
    max_attempts = max(1, max_attempts)

    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return execute_fn(*args, **kwargs)
        except (ApprovalRequired, ClarificationRequired, PermissionError) as e:
            # These are flow-control pauses or governance blocks — never retry
            raise
        except RuntimeError as e:
            # Guard blocks and turn/cost budget exhaustion are not retryable
            raise
        except TimeoutError as e:
            if "timeout" not in on_categories:
                raise
            last_exc = e
        except (json.JSONDecodeError, ValueError) as e:
            if "llm_parse_error" not in on_categories:
                raise
            last_exc = e
        except Exception as e:
            if "tool_error" not in on_categories:
                raise
            last_exc = e

        # Not on the last attempt — sleep before retry
        if attempt < max_attempts - 1:
            if backoff == "exponential":
                time.sleep(2 ** attempt)
            else:
                time.sleep(2)

    raise last_exc  # type: ignore[misc]


# ── block executor wrappers ───────────────────────────────────────────────────

def _execute_brain(
    block: dict,
    state: dict,
    compiled_artifacts: dict,
    credentials: dict | None = None,
    db=None,
    run_id: str | None = None,
    block_id: str | None = None,
    playbook_slug: str | None = None,
    injected_session=None,
    workspace_id: str = "",
    workflow_id: str | None = None,
    user_email: str | None = None,
    block_label: str | None = None,
    workflow_name: str | None = None,
    environment_id: str | None = None,
    attempt_id: str | None = None,
    resume_from_turn: int = 0,
) -> dict:
    from app.runtime.blocks.brain_block import _execute_brain as _brain_impl
    return _brain_impl(
        block, state, compiled_artifacts,
        credentials=credentials, db=db, run_id=run_id,
        block_id=block_id, playbook_slug=playbook_slug,
        injected_session=injected_session,
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        user_email=user_email,
        block_label=block_label,
        workflow_name=workflow_name,
        environment_id=environment_id,
        attempt_id=attempt_id,
        resume_from_turn=resume_from_turn,
    )


def _execute_tool(block: dict, state: dict, credentials: dict, allowed_hosts: list[str] | None = None, db=None, workspace_id: str = "") -> dict:
    from app.runtime.blocks.tool_block import _execute_tool as _tool_impl
    return _tool_impl(block, state, credentials, allowed_hosts=allowed_hosts, db=db, workspace_id=workspace_id)


def _execute_output(block: dict, state: dict, credentials: dict, workflow_name: str = "Agent", trace_url: str = "", run_id: str = "", workspace_id: str = "") -> dict:
    from app.runtime.blocks.output_block import _execute_output as _output_impl
    return _output_impl(block, state, credentials, workflow_name=workflow_name, trace_url=trace_url, run_id=run_id, workspace_id=workspace_id)


def _evaluate_condition_jinja(raw: str, state: dict) -> str | None:
    from app.runtime.blocks.logic_block import _evaluate_condition_jinja as _ecj_impl
    return _ecj_impl(raw, state)


def _execute_logic(block: dict, state: dict) -> dict:
    from app.runtime.blocks.logic_block import _execute_logic as _logic_impl
    return _logic_impl(block, state)


def _execute_approval(block: dict, state: dict, credentials: dict, run_id: str) -> dict:
    from app.runtime.blocks.approval_block import _execute_approval as _approval_impl
    return _approval_impl(block, state, credentials, run_id)


from app.runtime.blocks.guard_block import _execute_guard as _guard_impl


def _auto_guard_check(
    state: dict, db, run_id, block_id: str, block_type: str,
    workspace_id_str: str, version, user_email: str | None,
) -> None:
    """Fire guard check before brain/tool/output blocks using run-start cached policy."""
    if not state.get("__guard_enabled"):
        return
    cache = state.get("__guard_policy_cache__")
    if not cache:
        return
    try:
        slug = getattr(getattr(version, "workflow", None), "playbook_slug", None)
        wf_name = getattr(getattr(version, "workflow", None), "name", None) or slug
        _guard_block = {
            "id": f"__guard_{block_id}",
            "config": {"enforcement_mode": cache["enforcement_mode"]},
        }
        result = _guard_impl(
            _guard_block, state, workspace_id_str, db,
            run_id=run_id,
            playbook_slug=slug,
            workflow_id=str(version.workflow.id),
            user_email=user_email,
            workflow_name=wf_name,
            _policy_cache=cache,
        )
        state[f"__guard_{block_id}"] = result
        _emit(db, run_id, f"__guard_{block_id}", "guard_check", {
            "block_type":       block_type,
            "status":           result.get("status"),
            "rules_checked":    result.get("rules_checked", 0),
            "violations":       result.get("violations", 0),
            "enforcement_mode": result.get("enforcement_mode"),
            "warnings":         result.get("warnings", []),
            "audited":          result.get("audited", []),
        })
    except RuntimeError:
        raise  # block → propagate to halt the run
    except Exception as _ge:
        log.warning("guard.auto_check_failed", block_id=block_id, block_type=block_type, error=str(_ge))


def _execute_memory(block: dict, state: dict, db, run_id: str, workspace_id: str, playbook_slug: str, credentials: dict | None = None) -> dict:
    from app.runtime.blocks.memory_block import _execute_memory as _memory_impl
    return _memory_impl(block, state, db, run_id, workspace_id, playbook_slug, credentials)


def _execute_memory_inner(block: dict, state: dict, db, run_id: str, workspace_id: str, playbook_slug: str, credentials: dict | None = None) -> dict:
    from app.runtime.blocks.memory_block import _execute_memory_inner as _memory_inner_impl
    return _memory_inner_impl(block, state, db, run_id, workspace_id, playbook_slug)


def _execute_mcp(block: dict, state: dict, cred_store: object, workspace_id: str = "") -> dict:
    from app.runtime.blocks.mcp_block import _execute_mcp as _mcp_impl
    return _mcp_impl(block, state, cred_store, workspace_id=workspace_id)


# MCP tool name → (integration handle, REST action, param rename map)
# param rename map: MCP input key → REST param key (only keys that differ)
_MCP_REST_MAP: dict[str, tuple[str, str, dict]] = {
    "get_issue":          ("github", "fetch_issue",       {"issue_number": "issue_number"}),
    "get_repository":     ("github", "get_repo",          {"owner": "owner", "repo": "repo"}),
    "create_issue":       ("github", "create_issue",      {}),
    "create_pull_request":("github", "open_pull_request", {}),
    "fork_repository":    ("github", "fork_repo",         {}),
    "search_code":        ("github", "search_code",       {}),
    "post_message":       ("slack",  "post_message",      {}),
}


def _mcp_needs_fallback(result: dict) -> bool:
    if result.get("skipped"):
        return True
    err = str(result.get("error", ""))
    return "unknown tool" in err.lower() or "not registered" in err.lower()


def _mcp_rest_fallback(block: dict, state: dict, credentials: dict,
                       allowed_hosts, workspace_id: str) -> dict | None:
    config = (block.get("data") or {}).get("config") or {}
    tool_name = config.get("tool_name", "")
    entry = _MCP_REST_MAP.get(tool_name)
    if not entry:
        return None
    handle, action, _ = entry
    # Build a synthetic tool block for the existing REST dispatcher
    rest_block = {
        **block,
        "data": {
            **block.get("data", {}),
            "type": "tool",
            "integration": handle,
            "action": action,
            "config": {"action": action, "params": config.get("params") or config.get("inputs") or {}},
        },
    }
    try:
        return _execute_tool(rest_block, state, credentials,
                             allowed_hosts=allowed_hosts, workspace_id=workspace_id)
    except Exception as e:
        return {"error": str(e), "fallback": "rest"}


# ── for_each resolution ───────────────────────────────────────────────────────

def _resolve_as_list(expr: str, state: dict) -> list:
    """Resolve a Jinja-style ref or literal expression to a Python list."""
    resolved = _resolve_refs(expr, state)
    if isinstance(resolved, list):
        return resolved
    if isinstance(resolved, str):
        import json as _json
        try:
            parsed = _json.loads(resolved)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, TypeError):
            pass
    return []


# ── single-block dispatcher ───────────────────────────────────────────────────

def _dispatch_single_block(
    block: dict,
    state: dict,
    *,
    compiled: dict,
    credentials: dict,
    allowed_hosts,
    db,
    run_id,
    block_id: str,
    version,
    workspace_id_str: str,
    logic_routes: dict,
    _logic_routes_version_ref: list,  # mutable single-element list so we can mutate from caller
    sandbox_sessions: dict | None = None,
    user_email: str | None = None,
    env_id=None,
    attempt_id: str | None = None,
    resume_from_turn: int = 0,
) -> dict:
    if sandbox_sessions is None:
        sandbox_sessions = {}
    """
    Pure dispatch — maps a block's type to its executor and returns the result.

    This is extracted from the `_execute_dag` try-block so that for_each can
    call it per-item without duplicating the if/elif chain.

    ``logic_routes`` and ``_logic_routes_version_ref`` are passed by reference
    so that logic block executions inside for_each iterations still update the
    route map of the parent loop (though for_each over logic blocks is unusual).
    """
    from app.core.config import settings as _settings

    block_type = block["data"].get("type", "tool")

    # Resolve slug and workflow name once — used by brain, guard, and memory dispatch.
    slug = getattr(getattr(version, "workflow", None), "playbook_slug", None)
    _wf_name = getattr(getattr(version, "workflow", None), "name", None) or slug

    if block_type == "trigger":
        result: dict = {"triggered": True}
        if "github_issue" in state:
            result.update(state["github_issue"])
            result["github_issue"] = state["github_issue"]
        if "github_trigger" in state:
            result["github_trigger"] = state["github_trigger"]

    elif block_type == "sandbox":
        from app.runtime.blocks.sandbox_block import _execute_sandbox
        result = _execute_sandbox(block, state, credentials, sandbox_sessions)

    elif block_type == "brain":
        _auto_guard_check(state, db, run_id, block_id, "brain", workspace_id_str, version, user_email)

        _block_label = block["data"].get("label") or block_id
        _runs_in = block.get("data", {}).get("runs_in")
        _injected_session = sandbox_sessions.get(_runs_in) if _runs_in else None

        # Resolve complexity → max_turns from agent_config (standard across all playbooks)
        # Priority: block-level complexity > plan.complexity > plan_fix.complexity > default
        if not block.get("data", {}).get("max_turns"):
            _block_complexity = (
                block.get("data", {}).get("complexity")
                or (state.get("plan") or {}).get("complexity")
                or (state.get("plan_fix") or {}).get("complexity")
            )
            if _block_complexity:
                _budgets = _agent_config().get("turn_budgets", {})
                _resolved_turns = _budgets.get(_block_complexity) or _budgets.get("default") or 25
                block["data"] = {**block.get("data", {}), "max_turns": _resolved_turns}

        # Auto-provision sandbox based on plan_fix.complexity when sandbox=auto
        if block.get("data", {}).get("sandbox") == "auto" and _injected_session is None:
            _auto_key = f"__auto_{block_id}"
            if _auto_key in sandbox_sessions:
                _injected_session = sandbox_sessions[_auto_key]
            else:
                _complexity = (state.get("plan_fix") or {}).get("complexity", "small")

                # Inject complexity-derived turn budget — overrides YAML max_turns
                _budgets = _agent_config().get("turn_budgets", {})
                _derived_turns = _budgets.get(_complexity) or _budgets.get("default") or 25
                block["data"] = {**block.get("data", {}), "max_turns": _derived_turns}

                if _complexity in ("medium", "large"):
                    try:
                        from app.runtime.blocks.sandbox_block import _detect_provider
                        from app.core.credentials import fetch_credential as _fetch_cred_auto
                        # Fetch sandbox-relevant creds from broker for provider detection
                        _auto_cred_token = state.get("__cred_token__", "")
                        _auto_cred_url = state.get("__cred_api_url__", "")
                        _auto_handles = state.get("__cred_handles__", [])
                        _auto_sb_creds: dict = {h: _fetch_cred_auto(_auto_cred_token, h, _auto_cred_url) for h in _auto_handles}
                        # Honour explicit UI selection first, fall back to credential detection
                        _preferred = (block.get("data", {}).get("runs_on") or {}).get("provider") or ""
                        _provider = _preferred if _preferred in ("modal", "e2b") else _detect_provider(_auto_sb_creds)
                        if _provider:
                            from app.runtime.sandbox_session import create_session as _cs
                            _auto_session = _cs(None, _auto_sb_creds, runs_on={"provider": _provider})
                            sandbox_sessions[_auto_key] = _auto_session
                            _injected_session = _auto_session
                            _emit(db, run_id, block_id, "sandbox_routing", {
                                "decision": "container",
                                "complexity": _complexity,
                                "provider": _provider,
                                "reason": f"complexity={_complexity} → {_provider} sandbox auto-provisioned",
                            })
                        else:
                            _emit(db, run_id, block_id, "sandbox_routing", {
                                "decision": "managed",
                                "complexity": _complexity,
                                "reason": f"complexity={_complexity} but no sandbox credentials → proxy mode",
                            })
                    except Exception as _sb_err:
                        log.warning("executor.auto_sandbox_failed", block_id=block_id, error=str(_sb_err))
                        _emit(db, run_id, block_id, "sandbox_routing", {
                            "decision": "proxy_fallback",
                            "complexity": _complexity,
                            "reason": f"sandbox provision failed ({_sb_err}) → proxy mode",
                        })
                else:
                    _emit(db, run_id, block_id, "sandbox_routing", {
                        "decision": "managed",
                        "complexity": _complexity,
                        "reason": f"complexity={_complexity} → proxy mode",
                    })

        result = _execute_brain(block, state, compiled, credentials=credentials,
                                db=db, run_id=run_id, block_id=block_id,
                                playbook_slug=slug, injected_session=_injected_session,
                                workspace_id=workspace_id_str, workflow_id=str(version.workflow.id),
                                user_email=user_email, block_label=_block_label, workflow_name=_wf_name,
                                environment_id=str(env_id) if env_id else None,
                                attempt_id=attempt_id, resume_from_turn=resume_from_turn)

    elif block_type == "tool":
        _auto_guard_check(state, db, run_id, block_id, "tool", workspace_id_str, version, user_email)
        result = _execute_tool(block, state, credentials, allowed_hosts=allowed_hosts, db=db, workspace_id=workspace_id_str)

    elif block_type == "output":
        _auto_guard_check(state, db, run_id, block_id, "output", workspace_id_str, version, user_email)
        wf_name = version.workflow.name if version.workflow else "Agent"
        trace_url = (
            f"{_settings.app_url.rstrip('/')}/workflows/{version.workflow.id}/runs/{run_id}"
            if version.workflow else ""
        )
        result = _execute_output(block, state, credentials, workflow_name=wf_name, trace_url=trace_url, run_id=run_id, workspace_id=workspace_id_str)

    elif block_type == "logic":
        result = _execute_logic(block, state)
        logic_routes[block_id] = result.get("route", "pass")
        _logic_routes_version_ref[0] += 1

    elif block_type == "approval":
        result = _execute_approval(block, state, credentials, run_id)

    elif block_type == "memory":
        result = _execute_memory(
            block, state, db, run_id,
            str(workspace_id_str),
            version.workflow.playbook_slug or "",
            credentials=credentials,
        )

    elif block_type == "guard":
        # Guard is applied automatically before every brain/tool/output block.
        # An explicit guard block in YAML is a no-op — it's already covered.
        result = {"status": "skipped", "reason": "guard_applied_automatically"}

    elif block_type == "mcp":
        result = _execute_mcp(block, state, credentials, workspace_id=workspace_id_str)
        # Fall back to REST if MCP server not registered or returned unknown tool
        if _mcp_needs_fallback(result):
            rest = _mcp_rest_fallback(block, state, credentials, allowed_hosts, workspace_id_str)
            if rest is not None:
                result = rest

    elif block_type == "for_each":
        # Called per-item by the for_each expansion loop (lines ~1260).
        # Returns the current iteration item under its variable name so
        # downstream blocks can reference {{block_id.items[N].<item_var>}}.
        item_var = (block["data"].get("config") or {}).get("item_var", "item")
        result = {item_var: state.get(item_var), "__index": state.get("__for_each_index")}

    else:
        result = {"status": "skipped", "type": block_type}

    return result


# ── main DAG execution loop ───────────────────────────────────────────────────

def _execute_dag(
    *,
    run: Any,
    version: Any,
    initial_state: dict,
    db: Any,
    credentials: dict | None = None,
    allowed_hosts: list[str] | None = None,
    workspace_id_str: str = "",
    env_id=None,
) -> dict:
    """
    Execute the compiled DAG for a run, block by block.

    This is the inner execution loop extracted from ``execute_run`` so that
    the eval harness can call it directly with a pre-loaded run/version and a
    mock DB session — without touching real database loading, credential
    resolution, or analytics emission.

    Parameters
    ----------
    run:
        Run ORM object (already loaded and marked running).
    version:
        WorkflowVersion ORM object (already loaded, graph + compiled_artifacts set).
    initial_state:
        Starting state dict (may include prior block outputs for resume runs).
    db:
        SQLAlchemy session used for run/event writes within the loop.
    credentials:
        Decrypted credentials dict keyed by integration handle.
    allowed_hosts:
        Egress allowlist for tool blocks.  None means unrestricted.
    workspace_id_str:
        Workspace ID string forwarded to memory blocks.

    Returns
    -------
    dict
        Final accumulated state after all blocks have been executed (or
        execution has stopped due to failure/approval pause).
    """
    from app.runtime.executor import _detect_outcome

    if credentials is None:
        credentials = {}

    run_id = run.id

    # Resolve user email — from run state (set at trigger time) or triggered_by Clerk ID
    _user_email: str | None = initial_state.get("__user_email") or None
    if not _user_email:
        _raw_trigger = str(run.triggered_by or "")
        if _raw_trigger and not _raw_trigger.startswith(("manual", "webhook", "schedule", "cron")):
            try:
                from app.models.user import User as _User
                _u = db.query(_User).filter(_User.clerk_id == _raw_trigger).first()
                if _u:
                    _user_email = _u.email
            except Exception:
                pass

    graph = version.graph
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    ordered = _topological_sort(nodes, edges)
    cleanup_blocks = [n for n in ordered if n["data"].get("type") == "cleanup"]
    exec_blocks = [n for n in ordered if n["data"].get("type") != "cleanup"]

    state: dict[str, Any] = dict(initial_state)

    # Resume from checkpoint — load per-block state rows from DB.
    _checkpoint_outputs, _block_state_rows = _load_checkpoint(str(run_id), db)
    _completed_blocks: set[str] = {r.block_id for r in _block_state_rows if not r.partial}
    _partial_blocks: dict[str, Any] = {r.block_id: r for r in _block_state_rows if r.partial}

    if _checkpoint_outputs:
        # Merge completed block outputs back into state so downstream refs resolve.
        for _bid, _bout in _checkpoint_outputs.items():
            if _bout:
                state[_bid] = _bout
        log.info("run.resumed_from_checkpoint", run_id=run_id, completed_blocks=list(_completed_blocks))

    # Seed inputs defaults so {{inputs.x}} refs resolve for auto-triggered runs.
    # Always merge spec defaults first, then let caller-supplied values win.
    # This ensures CLI --input values override canvas-installed defaults.
    inputs_spec = graph.get("inputs_spec") or {}
    if inputs_spec:
        spec_defaults = {
            k: (v.get("default") if isinstance(v, dict) else v)
            for k, v in inputs_spec.items()
        }
        state["inputs"] = {**spec_defaults, **state.get("inputs", {})}

    failed = False
    fail_error = ""
    fail_summary: dict[str, Any] | None = None
    logic_routes: dict[str, str] = {}  # block_id → 'pass'|'fail'
    sandbox_sessions: dict[str, Any] = {}  # block_id → live session for sandbox blocks

    # Cache the skip set and only recompute when a new logic route is resolved.
    # Previously _find_skipped_blocks was called O(n) times (once per block),
    # each call itself O(n²), giving O(n³) total.  Now it is called at most
    # once per logic block output — O(n) calls total.
    _cached_skipped: set[str] = set()
    _logic_routes_version: int = 0

    for block in exec_blocks:
        # Check if user cancelled the run between blocks
        try:
            db.refresh(run)
        except Exception:
            pass
        if run.status == "cancelled":
            log.info("run.cancelled", run_id=run_id)
            return state

        block_id = block["id"]
        block_type = block["data"].get("type", "tool")

        # Skip blocks already completed in a previous run segment (resume support).
        # Source of truth is run_block_states (DB), with state dict as fallback for
        # legacy runs that only have the Redis/state blob.
        if block_id in _completed_blocks or (block_id not in _completed_blocks and block_id in state and block_id not in _partial_blocks):
            log.debug("block.skipped_resume", block_id=block_id)
            if block_type == "logic":
                _existing = state.get(block_id, {})
                logic_routes[block_id] = _existing.get("route", "pass") if isinstance(_existing, dict) else "pass"
                _logic_routes_version += 1
            continue

        # Recompute skip set only when logic_routes has been updated since last check
        if len(logic_routes) != _logic_routes_version or not _cached_skipped and logic_routes:
            _cached_skipped = _find_skipped_blocks(nodes, edges, logic_routes)
            _logic_routes_version = len(logic_routes)

        if block_id in _cached_skipped:
            _emit(db, run_id, block_id, "block_skipped", {"reason": "branch_not_taken"})
            continue

        run.current_block_id = block_id
        try:
            db.commit()
        except Exception:
            pass

        # Determine attempt_id: reuse from partial checkpoint row if resuming
        # mid-block, otherwise mint a fresh one. This keeps the attempt_id stable
        # across crash/resume so external services can use it as an idempotency key.
        _partial_row = _partial_blocks.get(block_id)
        _attempt_id: str = _partial_row.attempt_id if _partial_row else str(uuid.uuid4())
        _resume_from_turn: int = _partial_row.resume_from_turn if _partial_row else 0

        # Write a partial DB checkpoint before dispatch — records attempt_id so that
        # if we crash here the next resume picks up the same attempt_id instead of
        # generating a new one (which would cause duplicate Slack/GitHub side effects).
        _checkpoint_state(
            run_id, state, db=db,
            block_id=block_id, attempt_id=_attempt_id,
            partial=True, resume_from_turn=_resume_from_turn,
        )

        _emit(db, run_id, block_id, "block_started", {
            "type": block_type,
            "label": block["data"].get("label", ""),
            "attempt_id": _attempt_id,
        })

        compiled = version.compiled_artifacts or {}

        # Shared mutable container so _dispatch_single_block can update _logic_routes_version
        _lrv_ref = [_logic_routes_version]

        def _dispatch(blk: dict, blk_state: dict) -> dict:
            return _dispatch_single_block(
                blk, blk_state,
                compiled=compiled,
                credentials=credentials,
                allowed_hosts=allowed_hosts,
                db=db,
                run_id=run_id,
                block_id=blk["id"],
                version=version,
                workspace_id_str=workspace_id_str,
                logic_routes=logic_routes,
                _logic_routes_version_ref=_lrv_ref,
                sandbox_sessions=sandbox_sessions,
                user_email=_user_email,
                env_id=env_id,
                attempt_id=_attempt_id,
                resume_from_turn=_resume_from_turn,
            )

        try:
            # ── for_each expansion ────────────────────────────────────────────
            for_each_expr = (block["data"].get("config") or {}).get("for_each")
            if for_each_expr:
                items = _resolve_as_list(for_each_expr, state)
                item_var = (block["data"].get("config") or {}).get("item_var", "item")
                results_list = []
                for idx, item in enumerate(items[:500]):  # hard cap 500 items
                    item_state = {**state, item_var: item, "__for_each_index": idx}
                    item_result = _dispatch(block, item_state)
                    results_list.append(item_result)
                for_each_result = {"items": results_list, "count": len(results_list)}
                state[block_id] = for_each_result
                state["__last_output"] = json.dumps(for_each_result, default=str)
                _logic_routes_version = _lrv_ref[0]
                _emit(db, run_id, block_id, "block_completed", {
                    "output": for_each_result,
                    "for_each": True,
                    "items_count": len(results_list),
                })
                continue  # skip the normal single-execution path

            # ── per-block retry + fallback_block ─────────────────────────────
            retry_cfg = (block["data"].get("config") or {}).get("retry") or block["data"].get("retry")
            fallback_block_id = block["data"].get("fallback_block")

            try:
                if retry_cfg:
                    result = _with_retry(_dispatch, retry_cfg, block, dict(state))
                elif block_type == "output":
                    # Special-case output block: soft-fail so the run can continue
                    wf_name = version.workflow.name if version.workflow else "Agent"
                    trace_url = (
                        f"{settings.app_url.rstrip('/')}/workflows/{version.workflow.id}/runs/{run_id}"
                        if version.workflow else ""
                    )
                    try:
                        result = _execute_output(block, state, credentials, workflow_name=wf_name, trace_url=trace_url, run_id=run_id, workspace_id=workspace_id_str)
                    except Exception as out_err:
                        log.error("block.output_failed", block_id=block_id, error=str(out_err))
                        result = {"sent": False, "error": str(out_err)}
                        _emit(db, run_id, block_id, "block_completed", {"output": result, "warning": str(out_err)})
                        state[block_id] = result
                        state["__last_output"] = json.dumps(result, default=str)
                        _logic_routes_version = _lrv_ref[0]
                        continue
                else:
                    result = _dispatch(block, dict(state))

            except (ApprovalRequired, ClarificationRequired, PermissionError):
                raise  # flow-control — never swallow
            except Exception as _block_err:
                if fallback_block_id:
                    log.warning("block.fallback_triggered", block_id=block_id,
                                fallback=fallback_block_id, error=str(_block_err))
                    _emit(db, run_id, block_id, "block_failed", {
                        "error": str(_block_err), "fallback_block": fallback_block_id
                    })
                    state[block_id] = {"error": str(_block_err), "fallback_triggered": True}
                    state["__next_block"] = fallback_block_id
                    _logic_routes_version = _lrv_ref[0]
                    continue
                raise

            _logic_routes_version = _lrv_ref[0]
            state[block_id] = result
            state["__last_output"] = json.dumps(result, default=str)
            # Atomic DB upsert — marks block complete, clears partial flag
            _checkpoint_state(
                run_id, state, db=db,
                block_id=block_id, attempt_id=_attempt_id,
                partial=False, resume_from_turn=0,
            )
            # Mark as completed so the in-process resume set stays consistent
            _completed_blocks.add(block_id)
            _partial_blocks.pop(block_id, None)

            _emit(db, run_id, block_id, "block_completed", {
                "output": result,
                "attempt_id": _attempt_id,
            })

        except ClarificationRequired as cr:
            run.status = "paused_for_clarification"
            run.paused_at = _now()
            run.current_block_id = cr.block_id
            run.state = state
            try:
                db.commit()
            except Exception:
                pass
            _emit(db, run_id, cr.block_id, "clarification_requested", {
                "block_id": cr.block_id,
                "question": cr.question,
            })
            log.info("run.paused_for_clarification", run_id=run_id, block_id=cr.block_id)
            return state  # Exit without marking failed

        except ApprovalRequired as ap:
            run.status = "paused"
            run.paused_at = _now()
            run.current_block_id = ap.block_id
            run.state = state
            try:
                db.commit()
            except Exception:
                pass
            _emit(db, run_id, ap.block_id, "approval_requested", {
                "block_id": ap.block_id,
                "message": ap.message,
            })
            log.info("run.paused", run_id=run_id, block_id=ap.block_id)
            return state  # Exit without marking failed

        except PermissionError as e:
            blocked_host = str(e).split("'")[1] if "'" in str(e) else "unknown"
            log.warning("block.egress_blocked", block_id=block_id, host=blocked_host, run_id=run_id)
            if settings.sentry_dsn:
                import sentry_sdk
                with sentry_sdk.push_scope() as scope:
                    scope.set_tag("run_id", str(run_id))
                    scope.set_tag("blocked_host", blocked_host)
                    sentry_sdk.capture_exception(e)
            failed = True
            fail_summary = _classify_failure(e, block_id)
            fail_error = fail_summary["message"]
            _emit(db, run_id, block_id, "block_failed", {
                "error": fail_summary["message"],
                "failure": fail_summary,
                "reason_code": fail_summary["code"],
                "next_action": fail_summary["next_action"],
            })
            break

        except Exception as e:
            log.exception("block.failed", block_id=block_id)
            if settings.sentry_dsn:
                import sentry_sdk
                with sentry_sdk.push_scope() as scope:
                    scope.set_tag("run_id", str(run_id))
                    scope.set_tag("block_id", block_id)
                    scope.set_tag("workspace_id", str(workspace_id_str))
                    sentry_sdk.capture_exception(e)
            failed = True
            fail_summary = _classify_failure(e, block_id)
            fail_error = fail_summary["message"]
            _emit(db, run_id, block_id, "block_failed", {
                "error": fail_summary["message"],
                "failure": fail_summary,
                "reason_code": fail_summary["code"],
                "next_action": fail_summary["next_action"],
            })
            break

    # Tear down sandbox sessions before cleanup blocks
    for _sb_id, _sb_session in list(sandbox_sessions.items()):
        try:
            _sb_session.close()
            log.debug("sandbox_block.closed", block_id=_sb_id)
        except Exception as _sb_err:
            log.warning("sandbox_block.close_failed", block_id=_sb_id, error=str(_sb_err))

    # Always run cleanup blocks
    for block in cleanup_blocks:
        try:
            _emit(db, run_id, block["id"], "block_started", {"type": "cleanup"})
            result = _execute_tool(block, state, credentials, allowed_hosts=allowed_hosts, db=db, workspace_id=workspace_id_str)
            _emit(db, run_id, block["id"], "block_completed", {"output": result})
        except Exception as e:
            cleanup_summary = _classify_failure(e, block["id"])
            _emit(db, run_id, block["id"], "block_failed", {
                "error": str(e),
                "failure": cleanup_summary,
                "reason_code": cleanup_summary["code"],
                "next_action": cleanup_summary["next_action"],
            })

    run.status = "failed" if failed else "succeeded"
    run.completed_at = _now()
    run.current_block_id = None
    run.locked_at = None   # release the worker lock on normal completion
    run.locked_by = None
    run.state = state
    wf = getattr(version, "workflow", None) if version else None
    real_slug = getattr(wf, "playbook_slug", None)
    run.outcome = _detect_outcome(real_slug, state, run.status)
    try:
        db.commit()
    except Exception:
        pass

    if failed and not fail_summary and fail_error:
        fail_summary = _classify_failure(RuntimeError(fail_error), None)

    _emit(db, run_id, None, "run_completed" if not failed else "run_failed", {
        "status": run.status,
        "error": fail_error,
        "failure": fail_summary,
        "reason_code": fail_summary["code"] if fail_summary else None,
        "next_action": fail_summary["next_action"] if fail_summary else None,
        "stop_reason": fail_summary["stop_reason"] if fail_summary else None,
    })
    log.info("run.finished", run_id=run_id, status=run.status)

    return state
