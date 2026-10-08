"""
DAG runner — topological execution loop and block dispatch.

Dependency order: runtime → tool_engine → dag_runner → executor
"""
from __future__ import annotations

import json
import uuid
from typing import Any

import structlog

from app.core.config import settings
from app.core.credentials import CredentialStore  # re-exported for backward compat
from app.runtime.runtime import _emit, _now, _agent_config

log = structlog.get_logger(__name__)


# ── flow-control exceptions ───────────────────────────────────────────────────
from app.runtime.exceptions import ApprovalRequired, ClarificationRequired  # noqa: F401
from app.runtime.dag_failures import _classify_failure, _tee_block  # noqa: F401,E402  (re-exported)
from app.runtime.dag_checkpoint import (  # noqa: F401,E402  (re-exported)
    _STATE_CHECKPOINT_TTL, _checkpoint_state, _load_checkpoint, _redis_client, _redis_pool,
)
from app.runtime.dag_graph import _find_skipped_blocks, _topological_sort, _with_retry  # noqa: F401,E402
from app.runtime.dag_blocks import (  # noqa: F401,E402  (re-exported)
    _MCP_REST_MAP,
    _auto_guard_check,
    _evaluate_condition_jinja,
    _execute_approval,
    _execute_brain,
    _execute_logic,
    _execute_mcp,
    _execute_memory,
    _execute_memory_inner,
    _execute_output,
    _execute_tool,
    _guard_impl,
    _mcp_needs_fallback,
    _mcp_rest_fallback,
    _resolve_as_list,
)


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
        try:
            result = _execute_mcp(block, state, credentials, workspace_id=workspace_id_str)
            if _mcp_needs_fallback(result):
                raise RuntimeError(result.get("reason") or "mcp_fallback")
        except Exception as _mcp_err:
            rest = _mcp_rest_fallback(block, state, credentials, allowed_hosts, workspace_id_str)
            result = rest if rest is not None else {"error": str(_mcp_err)}

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
        _tee_block(run, block_id, "run.block_started", {
            "type": block_type,
            "label": block["data"].get("label", ""),
        })

        compiled = version.compiled_artifacts or {}

        # Shared mutable container so _dispatch_single_block can update _logic_routes_version
        _lrv_ref = [_logic_routes_version]

        def _dispatch(blk: dict, blk_state: dict) -> dict:
            from app.modules.auth.federation.workflow import check_run
            check_run(db, workspace_id_str, run_id, blk["id"])
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
                _tee_block(run, block_id, "run.block_completed", {
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
                        _tee_block(run, block_id, "run.block_completed", {"warning": str(out_err)})
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
                    _tee_block(run, block_id, "run.block_failed", {
                        "error": str(_block_err), "fallback_block": fallback_block_id,
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
            _tee_block(run, block_id, "run.block_completed", None)

            # Visibility: if any {{block.field}} refs in this block's inputs
            # failed to resolve, surface them so users don't only find out
            # by seeing literal {{...}} in prod output. state accumulates
            # per block, drain after emitting so downstream blocks start clean.
            _unresolved = state.pop("__unresolved_template_refs", None)
            if _unresolved:
                _dedup = sorted(set(_unresolved))
                _emit(db, run_id, block_id, "template_refs_unresolved", {
                    "refs": _dedup,
                    "count": len(_unresolved),
                })
                log.warning("template.unresolved_refs",
                            block_id=block_id, refs=_dedup)

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
            # #1480 PR 14 — surface the pause on the Lens session stream so
            # <RunBubble> can render Approve/Reject buttons inline.
            try:
                from app.modules.glens.run_events import publish_run_status
                publish_run_status(run)
            except Exception:
                pass
            _payload = {
                "block_id": ap.block_id,
                "message": ap.message,
            }
            if ap.metadata:
                _payload.update(ap.metadata)
            _emit(db, run_id, ap.block_id, "approval_requested", _payload)
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
            fail_summary = _classify_failure(e, block_id, state)
            fail_error = fail_summary["message"]
            _emit(db, run_id, block_id, "block_failed", {
                "error": fail_summary["message"],
                "failure": fail_summary,
                "reason_code": fail_summary["code"],
                "next_action": fail_summary["next_action"],
            })
            _tee_block(run, block_id, "run.block_failed", {
                "error": fail_summary["message"],
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
            fail_summary = _classify_failure(e, block_id, state)
            fail_error = fail_summary["message"]
            _emit(db, run_id, block_id, "block_failed", {
                "error": fail_summary["message"],
                "failure": fail_summary,
                "reason_code": fail_summary["code"],
                "next_action": fail_summary["next_action"],
            })
            _tee_block(run, block_id, "run.block_failed", {
                "error": fail_summary["message"],
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
            cleanup_summary = _classify_failure(e, block["id"], state)
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

    # #1480 PR 5 — tee terminal transition to Lens session stream when Lens-originated.
    try:
        from app.modules.glens.run_events import publish_run_status
        publish_run_status(run, error=fail_error if failed else None)
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
