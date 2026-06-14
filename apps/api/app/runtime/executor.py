"""
DAG Executor — runs a workflow version block by block.

Execution model:
- Topologically sort the graph
- Execute each block, passing accumulated state from previous blocks
- Logic blocks route execution: pass/fail source handles control which branch runs
- Approval blocks pause the run; resume via POST /runs/{id}/approve
- Write a run_event for every state transition
- On any failure, mark the run failed and run cleanup blocks
"""
import json
import os
import re
import socket
import subprocess
import time
import functools
import structlog
import yaml
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.runtime.llm_client import AnthropicClient, OpenAIClient, PerplexityClient, LLMTextBlock, LLMToolUseBlock
from app.runtime.model_router import resolve as _router_resolve
from app.runtime.pricing import freeze_pricing_snapshot, get_model_rates
from app.core.crypto import decrypt
from app.core.database import SessionLocal
from app.models.environment import Environment  # noqa: F401 — used for FK relationship loading
from app.models.integration import Integration
from app.models.run import Run, RunEvent
from app.models.workflow import WorkflowVersion

log = structlog.get_logger(__name__)

@functools.lru_cache(maxsize=1)
def _agent_config() -> dict:
    path = Path(__file__).parent / "agent_config.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


# ── helpers ──────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


class CredentialStore:
    """
    A dict-like wrapper around decrypted workspace credentials.

    Purpose: prevent secrets from leaking into logs, exception tracebacks,
    or Sentry breadcrumbs via accidental repr()/str() calls on the credentials
    object (e.g. log.error("ctx=%r", credentials)).

    Access via store["handle"] or store.get("handle") — values are returned
    normally.  repr() and str() return a placeholder with handle names only.
    """

    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data

    # Dict-like interface used by block executors
    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()

    def values(self):
        return self._data.values()

    def __iter__(self):
        return iter(self._data)

    def __len__(self) -> int:
        return len(self._data)

    # Safety: never expose values in repr/str
    def __repr__(self) -> str:
        return f"CredentialStore(handles={list(self._data.keys())})"

    def __str__(self) -> str:
        return self.__repr__()


_REDACT_PATTERNS = [
    # GitHub tokens
    (re.compile(r'ghp_[A-Za-z0-9]{36,}'), '[REDACTED-GITHUB-TOKEN]'),
    (re.compile(r'github_pat_[A-Za-z0-9_]{82,}'), '[REDACTED-GITHUB-TOKEN]'),
    (re.compile(r'ghs_[A-Za-z0-9]{36,}'), '[REDACTED-GITHUB-TOKEN]'),
    # Anthropic keys (sk-ant-api03-... contain dashes — must precede the generic sk- rule)
    (re.compile(r'sk-ant-[A-Za-z0-9_\-]{20,}'), '[REDACTED-ANTHROPIC-KEY]'),
    # OpenAI / generic sk- keys
    (re.compile(r'sk-[A-Za-z0-9]{32,}'), '[REDACTED-API-KEY]'),
    # Slack bot / user / app tokens
    (re.compile(r'xox[bpra]-[A-Za-z0-9\-]{10,}'), '[REDACTED-SLACK-TOKEN]'),
    # Bearer tokens in headers / strings
    (re.compile(r'Bearer\s+[A-Za-z0-9\-_\.]{20,}'), 'Bearer [REDACTED]'),
]


def _redact(text: str) -> str:
    for pattern, replacement in _REDACT_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _redact_payload(payload: dict) -> dict:
    """Recursively redact sensitive tokens from all string values in a payload."""
    out = {}
    for k, v in payload.items():
        if isinstance(v, str):
            out[k] = _redact(v)
        elif isinstance(v, dict):
            out[k] = _redact_payload(v)
        elif isinstance(v, list):
            out[k] = [_redact(i) if isinstance(i, str) else i for i in v]
        else:
            out[k] = v
    return out


def _write_trace(db, run_id, block_id: str, turn: int, role: str, **kwargs) -> None:
    """Write one run_trace row. Fire-and-forget — never raises."""
    try:
        from app.models.run_trace import RunTrace
        db.add(RunTrace(run_id=run_id, block_id=block_id, turn=turn, role=role, **kwargs))
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def _emit(db, run_id, block_id: str | None, kind: str, payload: dict):
    event = RunEvent(run_id=run_id, block_id=block_id, kind=kind, payload=_redact_payload(payload))
    db.add(event)
    db.commit()
    # Notify SSE subscribers that a new event is available
    from app.routers.runs import publish_run_event
    publish_run_event(str(run_id))


# ── Outcome detection ────────────────────────────────────────────────────────
# Maps playbook_slug → (outcome_type, artifact_url_keys, requires_artifact)
# requires_artifact=True: only record outcome if the artifact URL is found in state
# requires_artifact=False: record outcome on success regardless (the action itself is the outcome)
_OUTCOME_MAP: dict[str, tuple[str, list[str], bool]] = {
    "autopilot":              ("pr_opened",              ["pr_url"],   True),
    "autopilot_quick":        ("pr_opened",              ["pr_url"],   True),
    "autopilot_full":         ("pr_opened",              ["pr_url"],   True),
    "autopilot_approved":     ("pr_opened",              ["pr_url"],   True),
    "ai_ready":               ("pr_opened",              ["pr_url"],   True),
    "smoke_test":             ("pipeline_verified",      [],           False),
    "pr_reviewer":            ("review_completed",       [],           False),
    "copilot_reviewer":       ("review_completed",       [],           False),
    "security_scanner":       ("review_completed",       [],           False),
    "issue_triage":           ("issue_triaged",          [],           False),
    "ci_notify":              ("ci_alert_sent",          [],           False),
    "flaky_test_detective":   ("flaky_test_filed",       ["issue_url"], True),
    "release_readiness":      ("release_reviewed",       [],           False),
    "release_notes":          ("release_notes_drafted",  [],           False),
    "release_gating":         ("release_tagged",         ["tag_url"],  True),
    "incident_responder":     ("incident_investigated",  [],           False),
    "postmortem_drafter":     ("postmortem_drafted",     ["issue_url"], True),
    "dependency_updater":     ("dependency_updated",     ["pr_url"],   True),
    "security_patch_updater": ("security_patch_applied", ["pr_url"],   True),
    "docs_drift_detector":    ("docs_updated",           ["issue_url"], True),
    "terraform_reviewer":     ("terraform_reviewed",     [],           False),
    "multi_repo_scanner":     ("security_findings_fleet", ["aggregate.top_findings"], False),
    "dependency_audit":       ("deps_audited",            ["fetch_outdated.count"],   False),
    "bulk_pr_reviewer":       ("prs_reviewed",            ["fetch_prs.count"],        False),
    "multi_env_smoke_test":   ("smoke_fleet",             ["diff_results.summary"],   False),
}


def _find_artifact(state: dict, *keys: str) -> str | None:
    """Search state shallowly (top-level + one level deep) for the first URL value matching any key."""
    # Top-level first
    for key in keys:
        v = state.get(key)
        if isinstance(v, str) and v.startswith("http"):
            return v
    # One level into block outputs
    for block_val in state.values():
        if not isinstance(block_val, dict):
            continue
        for key in keys:
            v = block_val.get(key)
            if isinstance(v, str) and v.startswith("http"):
                return v
    return None


def _detect_outcome(playbook_slug: str | None, state: dict, run_status: str) -> dict | None:
    """
    Return a structured outcome dict for a completed run, or None if not applicable.
    Called after run.status is set. Only fires on succeeded runs with a known slug.
    """
    if run_status != "succeeded" or not playbook_slug:
        return None
    entry = _OUTCOME_MAP.get(playbook_slug)
    if not entry:
        return None
    outcome_type, artifact_keys, requires_artifact = entry
    artifact_url = _find_artifact(state, *artifact_keys) if artifact_keys else None
    if requires_artifact and not artifact_url:
        return None  # action didn't produce the expected artifact — don't miscount
    result: dict = {"type": outcome_type}
    if artifact_url:
        result["artifact_url"] = artifact_url
    return result


def _emit_run_analytics(run, version, state: dict, db, *, outcome: str, error: str = "") -> None:
    """
    Write one RunAnalyticsEvent row at the end of every run.
    Fire-and-forget — never raises, never blocks the run result.
    One row per run (not per block); feeds benchmark, eval harness, cross-tenant analytics.
    """
    try:
        import hashlib
        from app.models.run_analytics_event import RunAnalyticsEvent

        blocks_executed = sum(1 for k, v in state.items() if not k.startswith("__") and isinstance(v, dict))

        total_input = total_output = total_tools = 0
        total_cost: float | None = None
        human_verdict: str | None = None
        for k, v in state.items():
            if k.startswith("__") or not isinstance(v, dict):
                continue
            total_input  += v.get("input_tokens", 0) or 0
            total_output += v.get("output_tokens", 0) or 0
            total_tools  += v.get("turns", 0) or 0
            if v.get("cost_usd"):
                total_cost = (total_cost or 0) + float(v["cost_usd"])
            if "decision" in v:
                human_verdict = v["decision"]

        duration_ms: int | None = None
        if run.completed_at and run.created_at:
            duration_ms = int((run.completed_at - run.created_at).total_seconds() * 1000)

        wf = getattr(version, "workflow", None) if version else None
        # Use the actual playbook_slug column; fall back to name-derived slug for custom workflows
        playbook_slug = (
            getattr(wf, "playbook_slug", None)
            or re.sub(r"[^a-z0-9]+", "_", (getattr(wf, "name", None) or "custom").lower()).strip("_")
            or "custom"
        )

        raw_trigger = str(run.triggered_by or "manual")
        if raw_trigger.startswith("webhook"):
            trigger_type = "webhook"
        elif raw_trigger.startswith(("schedule", "cron")):
            trigger_type = "cron"
        else:
            trigger_type = "manual"

        workspace_raw = str(getattr(wf, "workspace_id", run.id) if wf else run.id)
        workspace_hash = hashlib.sha256(workspace_raw.encode()).hexdigest()[:16]

        db.add(RunAnalyticsEvent(
            run_id=run.id,
            workspace_id=workspace_hash,
            playbook_slug=playbook_slug,
            model=state.get("__model") or "unknown",
            trigger_type=trigger_type,
            blocks_executed=blocks_executed,
            tool_calls=total_tools,
            input_tokens=total_input,
            output_tokens=total_output,
            duration_ms=duration_ms,
            outcome=outcome,
            human_verdict=human_verdict,
            cost_usd=total_cost,
            error=error[:2000] if error else None,
        ))
        db.commit()
        log.debug("run_analytics.written", run_id=str(run.id), outcome=outcome)
    except Exception:
        log.exception("run_analytics.failed")


_ONLINE_EVAL_QUEUE = "marshal:eval:online:queue"
_ONLINE_EVAL_QUEUE_MAX = 10_000  # cap to prevent unbounded growth when worker is down


def _enqueue_online_eval(run_id: str) -> None:
    """Push run_id to the online eval queue. Fire-and-forget — never raises."""
    try:
        import redis as _redis
        r = _redis.from_url(settings.redis_url, decode_responses=True)
        qlen = r.llen(_ONLINE_EVAL_QUEUE)
        if qlen >= _ONLINE_EVAL_QUEUE_MAX:
            log.warning("online_eval.queue_full", queue_len=qlen, run_id=run_id)
            return
        r.rpush(_ONLINE_EVAL_QUEUE, run_id)
    except Exception:
        log.warning("online_eval.enqueue_failed", run_id=run_id)


def _resolve_refs(value: Any, state: dict) -> Any:
    """Replace {{block_id.field}} references with values from run state."""
    if isinstance(value, str):
        _MISSING = object()

        def replace(m):
            parts = m.group(1).split(".")
            obj = state.get(parts[0], _MISSING)
            if obj is _MISSING:
                log.debug("unresolved_template_ref", ref=m.group(1), top_key=parts[0])
                return m.group(0)
            for p in parts[1:]:
                if isinstance(obj, dict):
                    nxt = obj.get(p, _MISSING)
                    if nxt is _MISSING:
                        log.debug("unresolved_template_ref", ref=m.group(1), missing_key=p)
                        return m.group(0)
                    obj = nxt
            return str(obj)

        return re.sub(r"\{\{([\w.]+)\}\}", replace, value)
    if isinstance(value, dict):
        return {k: _resolve_refs(v, state) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve_refs(i, state) for i in value]
    return value


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
    of block IDs that should be skipped because they're on the non-taken branch.

    A block is skipped if:
    1. It is the direct target of a wrong-route edge from a logic block, OR
    2. ALL of its incoming edges come from skipped blocks (propagation).
    """
    if not logic_routes:
        return set()

    all_node_ids = {n["id"] for n in nodes}
    skipped: set[str] = set()

    # Direct targets of non-chosen branches
    for edge in edges:
        src = edge.get("source", "")
        if src in logic_routes:
            handle = edge.get("sourceHandle") or "pass"
            if handle != logic_routes[src]:
                skipped.add(edge["target"])

    # Propagate: if every incoming edge comes from a skipped node, skip this node too
    changed = True
    while changed:
        changed = False
        for node_id in all_node_ids:
            if node_id in skipped:
                continue
            incoming = [e for e in edges if e["target"] == node_id]
            if incoming and all(e["source"] in skipped for e in incoming):
                skipped.add(node_id)
                changed = True

    return skipped


# ── special exceptions ────────────────────────────────────────────────────────

class ApprovalRequired(Exception):
    """Raised by the approval block to pause the run."""
    def __init__(self, block_id: str, message: str = ""):
        self.block_id = block_id
        self.message = message
        super().__init__(message)


class ClarificationRequired(Exception):
    """Raised by a Brain block when the task context is too ambiguous to proceed."""
    def __init__(self, block_id: str, question: str):
        self.block_id = block_id
        self.question = question
        super().__init__(question)


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

    return {
        "code": code,
        "category": category,
        "stop_reason": stop_reason,
        "message": msg,
        "block_id": block_id,
        "next_action": next_action,
    }


def _with_retry(execute_fn, retry_cfg: dict, *args, **kwargs):
    """
    Wrap execute_fn with per-block retry logic.

    retry_cfg keys:
      max      — int, total attempts (default 1 = no retry)
      backoff  — "fixed" | "exponential"  (default "fixed")
      on       — list of error categories to retry: "tool_error" | "timeout"
                 (default ["tool_error", "timeout"])
    """
    max_attempts = int(retry_cfg.get("max", 1))
    backoff = retry_cfg.get("backoff", "fixed")
    on_categories = set(retry_cfg.get("on", ["tool_error", "timeout"]))

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


# ── tool definitions for Brain agentic mode ───────────────────────────────────

BRAIN_TOOLS = [
    {
        "name": "read_file",
        "description": "Read the contents of a file at the given path.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative file path to read"}
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file at the given path. Creates parent directories if needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write to the file"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "run_shell",
        "description": "Execute a shell command and return stdout/stderr. Use for tests, builds, git commands.",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "working_dir": {"type": "string", "description": "Working directory (optional)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "search_code",
        "description": "Search for a pattern in files using grep. Returns matching lines with file paths.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Directory or file to search in", "default": "."},
                "file_glob": {"type": "string", "description": "File glob to filter (e.g. '*.py')", "default": "*"},
            },
            "required": ["pattern"],
        },
    },
]

# Commands that are never allowed in run_shell.
# These are last-resort guards — the Brain block runs in Modal sandbox for
# production workloads.  Local execution should still be hardened.
_FORBIDDEN_SHELL_PATTERNS = [
    # Filesystem destruction
    r"rm\s+-[rRfF]*r[rRfF]*\s+/",  # rm -rf / and variants
    r"mkfs",
    r"dd\s+if=",
    r">\s*/dev/sd",
    r"chmod\s+777\s+/",
    r"chown.*root",
    # Fork bomb
    r":\(\)\{.*\}",
    # Pipe-to-shell (download + execute)
    r"(curl|wget)\s+.*\|\s*(bash|sh|python|perl|ruby|node)",
    # Reverse shell patterns
    r"/dev/tcp/",           # bash -i >& /dev/tcp/HOST/PORT
    r"nc\s+.*-[el]",        # netcat listener/execute mode
    r"socat\s+.*exec",
    # Python/Perl/Ruby one-liners executing arbitrary code
    r"python[23]?\s+-c\s+['\"]?import\s+os",
    r"perl\s+-e\s+.*exec",
    r"ruby\s+-e\s+.*exec",
]

# Environment variables stripped from the subprocess environment so that
# secrets injected into the worker process cannot be read via `env`, `printenv`,
# or /proc/self/environ by LLM-generated commands.
_SECRET_ENV_VARS = {
    "ANTHROPIC_API_KEY",
    "ENCRYPTION_KEY",
    "DATABASE_URL",
    "REDIS_URL",
    "CLERK_SECRET_KEY",
    "CLERK_FRONTEND_API",
    "GITHUB_WEBHOOK_SECRET",
    "VERCEL_WEBHOOK_SECRET",
    "SLACK_SIGNING_SECRET",
    "CLI_API_KEY",
    "RESEND_API_KEY",
    "ADMIN_SECRET",
    "MODAL_TOKEN_ID",
    "MODAL_TOKEN_SECRET",
    "OPENAI_API_KEY",
    "VOYAGE_API_KEY",
    "SENTRY_DSN",
    "RAILWAY_API_TOKEN",
}


def _safe_subprocess_env() -> dict:
    """Return os.environ with all known secret variables stripped out.

    This prevents LLM-generated shell commands from reading process secrets
    via `env`, `printenv`, or `/proc/self/environ`.
    """
    return {k: v for k, v in os.environ.items() if k not in _SECRET_ENV_VARS}


def _tool_read_file(path: str) -> str:
    try:
        with open(path) as f:
            content = f.read()
        if len(content) > 20_000:
            content = content[:20_000] + "\n[... truncated]"
        return content
    except Exception as e:
        return f"Error reading file: {e}"


def _tool_write_file(path: str, content: str) -> str:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Written {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error writing file: {e}"


def _tool_run_shell(command: str, working_dir: str | None = None) -> str:
    for pattern in _FORBIDDEN_SHELL_PATTERNS:
        if re.search(pattern, command, re.IGNORECASE):
            return f"Refused: command matches forbidden pattern '{pattern}'"
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=working_dir,
            env=_safe_subprocess_env(),  # strip secrets from subprocess environment
        )
        output = result.stdout + result.stderr
        if len(output) > 10_000:
            output = output[:10_000] + "\n[... truncated]"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out after 60s"
    except Exception as e:
        return f"Error running shell: {e}"


def _tool_search_code(pattern: str, path: str = ".", file_glob: str = "*") -> str:
    try:
        cmd = ["grep", "-r", "--include", file_glob, "-n", pattern, path]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        output = result.stdout
        if len(output) > 8_000:
            output = output[:8_000] + "\n[... truncated]"
        return output or "(no matches)"
    except Exception as e:
        return f"Error searching: {e}"


def _dispatch_tool(tool_name: str, tool_input: dict, remote_host: dict | None = None, credentials: dict | None = None) -> str:
    from app.runtime.sandbox import dispatch_brain_tool
    return dispatch_brain_tool(tool_name, tool_input, remote_host=remote_host, credentials=credentials)


def _resolve_remote_host(
    block: dict, state: dict, credentials: dict
) -> dict | None:
    """
    If a Brain block declares a remote_host in its config, resolve it into a
    concrete dict suitable for passing to ``dispatch_brain_tool``.

    Block config shape:
        {
            "remote_host": {
                "ip_ref": "{{wait.ip_address}}",           # required
                "credentials_from": "digitalocean",        # integration handle
                "username": "root",                        # optional, default root
                "port": 22                                 # optional, default 22
            }
        }

    The SSH private key is *never* embedded in the workflow JSON — it is read
    from the named integration's encrypted credentials at execution time.
    Returns None when no remote_host is configured (block runs locally / in Modal).
    """
    cfg = block.get("data", {}).get("config", {}) or {}
    rh = cfg.get("remote_host")
    if not rh:
        return None

    ip_ref = rh.get("ip_ref") or rh.get("ip")
    ip = _resolve_refs(ip_ref, state) if isinstance(ip_ref, str) else ip_ref
    if not ip or (isinstance(ip, str) and ip.startswith("{{")):
        # Couldn't resolve — fall back to local execution rather than fail the block.
        log.warning("brain.remote_host_unresolved", block_id=block.get("id"), ip_ref=ip_ref)
        return None

    handle = rh.get("credentials_from") or "digitalocean"
    creds = credentials.get(handle, {}) if isinstance(credentials, dict) else {}
    private_key = creds.get("ssh_private_key") or rh.get("private_key")
    if not private_key:
        log.warning("brain.remote_host_no_key", block_id=block.get("id"), credentials_from=handle)
        return None

    return {
        "ip": ip,
        "username": rh.get("username") or creds.get("ssh_username") or "root",
        "port": int(rh.get("port") or creds.get("ssh_port") or 22),
        "private_key": private_key,
        "private_key_passphrase": creds.get("ssh_private_key_passphrase"),
    }


# ── block executors ───────────────────────────────────────────────────────────

def _extract_git_evidence(working_dir: str | None) -> tuple[list[dict], str]:
    """Run git diff --stat in working_dir. Returns (files_changed, diff_stat_text)."""
    if not working_dir:
        return [], ""
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            capture_output=True, text=True, timeout=10, cwd=working_dir,
        )
        stat = result.stdout.strip()
        if not stat:
            # Nothing committed yet — diff against index
            result = subprocess.run(
                ["git", "diff", "--stat"],
                capture_output=True, text=True, timeout=10, cwd=working_dir,
            )
            stat = result.stdout.strip()

        files: list[dict] = []
        for line in stat.splitlines():
            line = line.strip()
            if "|" in line:
                path = line.split("|")[0].strip()
                action = "modified"
                if "new file" in line.lower():
                    action = "created"
                elif "deleted" in line.lower():
                    action = "deleted"
                files.append({"path": path, "action": action})
        return files, stat
    except Exception:
        return [], ""


def _summarise_tool_call(tool_name: str, tool_input: dict) -> str:
    """Return a short human-readable description of a single tool call."""
    if tool_name == "run_shell":
        cmd = tool_input.get("command", "")
        wd = tool_input.get("working_dir", "")
        return f"$ {cmd}" + (f"  (in {wd})" if wd else "")
    if tool_name == "write_file":
        return f"write {tool_input.get('path', '')}"
    if tool_name == "read_file":
        return f"read {tool_input.get('path', '')}"
    return tool_name


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
) -> dict:
    from app.runtime.blocks.brain_block import _execute_brain as _brain_impl
    return _brain_impl(
        block, state, compiled_artifacts,
        credentials=credentials, db=db, run_id=run_id,
        block_id=block_id, playbook_slug=playbook_slug,
        injected_session=injected_session,
    )

def _dry_run_mock(integration: str, action: str, params: dict) -> dict:
    """Return a realistic-looking mock result for dry run mode."""
    return {
        "dry_run": True,
        "integration": integration,
        "action": action,
        "params": params,
        "simulated": True,
        "note": f"Dry run — {integration}.{action} would have been called with these params",
    }


_INTEGRATION_HOSTS: dict[str, str] = {
    "github": "api.github.com",
    "slack": "slack.com",
    "linear": "api.linear.app",
    "digitalocean": "api.digitalocean.com",
    "vercel": "api.vercel.com",
    "railway": "backboard.railway.app",
}


def _check_egress(host: str, allowed_hosts: list[str] | None) -> None:
    """Raise PermissionError if host is not in the environment's allowlist."""
    if not allowed_hosts:
        return
    for pattern in allowed_hosts:
        if pattern.startswith("*."):
            if host == pattern[2:] or host.endswith("." + pattern[2:]):
                return
        elif host == pattern:
            return
    raise PermissionError(f"Host {host!r} is not in this environment's allowed_hosts list")


def _execute_tool(block: dict, state: dict, credentials: dict, allowed_hosts: list[str] | None = None, db=None, workspace_id: str = "") -> dict:
    from app.runtime.blocks.tool_block import _execute_tool as _tool_impl
    return _tool_impl(block, state, credentials, allowed_hosts=allowed_hosts, db=db, workspace_id=workspace_id)

def _build_run_summary(state: dict) -> str:
    """Build a human-readable bullet-point summary from accumulated block outputs."""
    lines = []

    # Prepend finding context when triggered by a security finding
    trigger = state.get("_trigger") or {}
    if trigger.get("finding_id"):
        sev = str(trigger.get("severity") or "unknown").upper()
        ftype = trigger.get("type") or "finding"
        repo = trigger.get("repo_full_name") or ""
        loc = trigger.get("file") or ""
        if trigger.get("line"):
            loc = f"{loc}:{trigger['line']}"
        desc = str(trigger.get("description") or "")[:120]
        tool = trigger.get("tool") or ""
        parts = [f"*Triggered by:* [{sev}] {ftype}"]
        if repo:
            parts.append(f"Repo: {repo}")
        if loc:
            parts.append(f"File: {loc}")
        if tool:
            parts.append(f"Tool: {tool}")
        if desc:
            parts.append(f"Finding: {desc}")
        lines.append("\n".join(parts))
        lines.append("")  # blank separator

    for key, val in state.items():
        if key.startswith("__"):
            continue
        if not isinstance(val, dict):
            continue
        # Skip skipped/dry-run blocks
        if val.get("skipped") or val.get("dry_run"):
            continue
        # Pick best one-liner
        summary = None
        if val.get("pr_url"):
            summary = f"PR opened → {val['pr_url']}"
        elif val.get("html_url") and val.get("clone_url"):
            summary = f"Repo created → {val['html_url']}"
        elif val.get("branch"):
            summary = f"Branch created: {val['branch']}"
        elif val.get("full_name"):
            summary = f"Repo: {val['full_name']}"
        elif val.get("ts") and val.get("channel"):
            summary = f"Slack message sent to {val['channel']}"
        elif val.get("identifier") and val.get("title"):
            summary = f"Linear {val['identifier']}: {val['title']}"
        elif val.get("droplet_id"):
            summary = f"Droplet {val['droplet_id']} — {val.get('status', '?')}"
        elif val.get("state") and val.get("url"):
            summary = f"Deployment {val['state']} → {val['url']}"
        elif val.get("triggered") and val.get("service_id"):
            summary = f"Railway service {val['service_id']} redeployed"
        elif val.get("route"):
            route = val["route"]
            summary = f"→ {route}" if route in ("pass", "fail") else f"Logic route: {route}"
        elif isinstance(val.get("output"), str):
            summary = val["output"][:120]
        if summary:
            lines.append(f"• {key}: {summary}")
    return "\n".join(lines) if lines else "No results recorded."


def _load_template(name: str) -> str:
    import os
    path = os.path.join(os.path.dirname(__file__), "..", "templates", name)
    try:
        with open(os.path.abspath(path)) as f:
            return f.read()
    except FileNotFoundError:
        return "{run_summary}"


def _fill_template(template: str, state: dict, workflow_name: str = "Agent", trace_url: str = "") -> tuple[str, str]:
    """Return (subject, body) filled from template."""
    run_summary = _build_run_summary(state)
    triggered_by = str(state.get("__triggered_by", "manual"))

    # Split subject line if present (first line starting with "Subject:")
    lines = template.strip().splitlines()
    subject = f"Conduct AI: {workflow_name} completed"
    body_lines = lines
    if lines and lines[0].lower().startswith("subject:"):
        subject = lines[0][8:].strip()
        body_lines = lines[2:] if len(lines) > 2 else []

    body = "\n".join(body_lines)
    replacements = {
        "{workflow_name}": workflow_name,
        "{status}": "completed",
        "{duration}": "—",
        "{triggered_by}": triggered_by,
        "{run_summary}": run_summary,
        "{trace_url}": trace_url or "(see Conduct AI dashboard)",
    }
    for k, v in replacements.items():
        subject = subject.replace(k, v)
        body = body.replace(k, v)

    return subject, body


def _execute_output(block: dict, state: dict, credentials: dict, workflow_name: str = "Agent", trace_url: str = "", run_id: str = "") -> dict:
    from app.runtime.blocks.output_block import _execute_output as _output_impl
    return _output_impl(block, state, credentials, workflow_name=workflow_name, trace_url=trace_url, run_id=run_id)

def _evaluate_condition_jinja(raw: str, state: dict) -> str | None:
    from app.runtime.blocks.logic_block import _evaluate_condition_jinja as _ecj_impl
    return _ecj_impl(raw, state)

def _execute_logic(block: dict, state: dict) -> dict:
    from app.runtime.blocks.logic_block import _execute_logic as _logic_impl
    return _logic_impl(block, state)

def _execute_approval(block: dict, state: dict, credentials: dict, run_id: str) -> dict:
    from app.runtime.blocks.approval_block import _execute_approval as _approval_impl
    return _approval_impl(block, state, credentials, run_id)

def _execute_guard(block: dict, state: dict, workspace_id: str, db) -> dict:
    from app.runtime.blocks.guard_block import _execute_guard as _guard_impl
    return _guard_impl(block, state, workspace_id, db)

# ── main executor ─────────────────────────────────────────────────────────────

def _execute_memory(block: dict, state: dict, db, run_id: str, workspace_id: str, playbook_slug: str, credentials: dict | None = None) -> dict:
    from app.runtime.blocks.memory_block import _execute_memory as _memory_impl
    return _memory_impl(block, state, db, run_id, workspace_id, playbook_slug, credentials)

def _execute_memory_inner(block: dict, state: dict, db, run_id: str, workspace_id: str, playbook_slug: str, credentials: dict | None = None) -> dict:
    from app.runtime.blocks.memory_block import _execute_memory_inner as _memory_inner_impl
    return _memory_inner_impl(block, state, db, run_id, workspace_id, playbook_slug, credentials)

def _execute_mcp(block: dict, state: dict, cred_store: object) -> dict:
    from app.runtime.blocks.mcp_block import _execute_mcp as _mcp_impl
    return _mcp_impl(block, state, cred_store)

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
    block_type = block["data"].get("type", "tool")

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
        if block.get("data", {}).get("isAgentic", False):
            if state.get("__guard_enabled", True):
                try:
                    import uuid as _uuid
                    from app.modules.guard.models import GuardConfig as _GuardConfig
                    _ws_str = str(workspace_id_str)
                    _gc = (
                        db.query(_GuardConfig)
                        .filter(_GuardConfig.workspace_id == _uuid.UUID(_ws_str))
                        .first()
                    ) if _ws_str else None
                    if _gc:
                        _guard_block = {
                            "id": f"__guard_{block_id}",
                            "config": {"enforcement_mode": _gc.enforcement_mode},
                        }
                        _guard_result = _execute_guard(_guard_block, state, _ws_str, db)
                        state[f"__guard_{block_id}"] = _guard_result
                        _emit(db, run_id, f"__guard_{block_id}", "guard_check", {
                            "status": _guard_result.get("status"),
                            "rules_checked": _guard_result.get("rules_checked", 0),
                            "violations": _guard_result.get("violations", 0),
                            "enforcement_mode": _guard_result.get("enforcement_mode"),
                            "warnings": _guard_result.get("warnings", []),
                        })
                except RuntimeError:
                    raise
                except Exception as _ge:
                    log.warning("guard.auto_hook_failed", block_id=block_id, error=str(_ge))

        slug = getattr(getattr(version, "workflow", None), "playbook_slug", None)
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
                        # Honour explicit UI selection first, fall back to credential detection
                        _preferred = (block.get("data", {}).get("runs_on") or {}).get("provider") or ""
                        _provider = _preferred if _preferred in ("modal", "e2b") else _detect_provider(credentials)
                        if _provider:
                            from app.runtime.sandbox_session import create_session as _cs
                            _auto_session = _cs(None, credentials, runs_on={"provider": _provider})
                            sandbox_sessions[_auto_key] = _auto_session
                            _injected_session = _auto_session
                            _emit(db, run_id, block_id, "sandbox_routing", {
                                "decision": "sandbox",
                                "complexity": _complexity,
                                "provider": _provider,
                                "reason": f"complexity={_complexity} → {_provider} sandbox auto-provisioned",
                            })
                        else:
                            _emit(db, run_id, block_id, "sandbox_routing", {
                                "decision": "proxy",
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
                        "decision": "proxy",
                        "complexity": _complexity,
                        "reason": f"complexity={_complexity} → proxy mode",
                    })

        result = _execute_brain(block, state, compiled, credentials=credentials,
                                db=db, run_id=run_id, block_id=block_id,
                                playbook_slug=slug, injected_session=_injected_session)

    elif block_type == "tool":
        result = _execute_tool(block, state, credentials, allowed_hosts=allowed_hosts, db=db, workspace_id=workspace_id_str)

    elif block_type == "output":
        wf_name = version.workflow.name if version.workflow else "Agent"
        trace_url = (
            f"{settings.app_url.rstrip('/')}/workflows/{version.workflow.id}/runs/{run_id}"
            if version.workflow else ""
        )
        result = _execute_output(block, state, credentials, workflow_name=wf_name, trace_url=trace_url, run_id=run_id)

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
        result = _execute_guard(block, state, str(workspace_id_str), db)
        _emit(db, run_id, block_id, "guard_check", {
            "status":           result.get("status"),
            "rules_checked":    result.get("rules_checked", 0),
            "violations":       result.get("violations", 0),
            "enforcement_mode": result.get("enforcement_mode"),
            "warnings":         result.get("warnings", []),
            "team_name":        result.get("team_name"),
        })

    elif block_type == "mcp":
        result = _execute_mcp(block, state, credentials)

    elif block_type == "for_each":
        # Called per-item by the for_each expansion loop (lines ~1260).
        # Returns the current iteration item under its variable name so
        # downstream blocks can reference {{block_id.items[N].<item_var>}}.
        item_var = (block["data"].get("config") or {}).get("item_var", "item")
        result = {item_var: state.get(item_var), "__index": state.get("__for_each_index")}

    else:
        result = {"status": "skipped", "type": block_type}

    return result


def _execute_dag(
    *,
    run: Any,
    version: Any,
    initial_state: dict,
    db: Any,
    credentials: dict | None = None,
    allowed_hosts: list[str] | None = None,
    workspace_id_str: str = "",
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
    if credentials is None:
        credentials = {}

    run_id = run.id
    graph = version.graph
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    ordered = _topological_sort(nodes, edges)
    cleanup_blocks = [n for n in ordered if n["data"].get("type") == "cleanup"]
    exec_blocks = [n for n in ordered if n["data"].get("type") != "cleanup"]

    state: dict[str, Any] = dict(initial_state)

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

        # Skip blocks already completed in a previous run segment (resume support)
        if block_id in state:
            log.debug("block.skipped_resume", block_id=block_id)
            if block_type == "logic":
                logic_routes[block_id] = state[block_id].get("route", "pass")
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

        _emit(db, run_id, block_id, "block_started", {
            "type": block_type,
            "label": block["data"].get("label", ""),
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

            # ── per-block retry ───────────────────────────────────────────────
            retry_cfg = (block["data"].get("config") or {}).get("retry")

            if retry_cfg:
                result = _with_retry(_dispatch, retry_cfg, block, state)
            else:
                # Special-case output block: soft-fail so the run can continue
                if block_type == "output":
                    wf_name = version.workflow.name if version.workflow else "Agent"
                    trace_url = (
                        f"{settings.app_url.rstrip('/')}/workflows/{version.workflow.id}/runs/{run_id}"
                        if version.workflow else ""
                    )
                    try:
                        result = _execute_output(block, state, credentials, workflow_name=wf_name, trace_url=trace_url, run_id=run_id)
                    except Exception as out_err:
                        log.error("block.output_failed", block_id=block_id, error=str(out_err))
                        result = {"sent": False, "error": str(out_err)}
                        _emit(db, run_id, block_id, "block_completed", {"output": result, "warning": str(out_err)})
                        state[block_id] = result
                        state["__last_output"] = json.dumps(result, default=str)
                        _logic_routes_version = _lrv_ref[0]
                        continue
                else:
                    result = _dispatch(block, state)

            _logic_routes_version = _lrv_ref[0]
            state[block_id] = result
            state["__last_output"] = json.dumps(result, default=str)

            _emit(db, run_id, block_id, "block_completed", {"output": result})

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
            fail_error = str(e)
            fail_summary = _classify_failure(e, block_id)
            _emit(db, run_id, block_id, "block_failed", {
                "error": str(e),
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
            fail_error = str(e)
            fail_summary = _classify_failure(e, block_id)
            _emit(db, run_id, block_id, "block_failed", {
                "error": str(e),
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



def _feedback_to_security_finding(run: "Run", db) -> None:
    """Connection 3 — write run outcome back to the linked SecurityFinding.

    Fires for runs triggered by the Security Loop or automation workflow.
    Updates finding.status: succeeded → fixed, failed → open (re-open for retry).
    """
    triggered_by = getattr(run, "triggered_by", None) or ""
    if triggered_by not in ("security_finding", "security_finding_automation"):
        return

    state = getattr(run, "state", None) or {}
    trigger = state.get("_trigger") or {}
    finding_id_str = trigger.get("finding_id")
    if not finding_id_str:
        return

    try:
        import uuid as _uuid
        from app.models.security_finding import SecurityFinding

        finding_uuid = _uuid.UUID(finding_id_str)
        finding = db.query(SecurityFinding).filter(SecurityFinding.id == finding_uuid).with_for_update().first()
        if not finding:
            return

        trigger_event = trigger.get("event_type", "")
        autopilot = trigger.get("autopilot_enabled", False)

        if run.status == "succeeded":
            # security_finding runs = triage; only mark fixed if autopilot actually patched it
            # security_finding_automation runs (incident-response workflow) = handled
            if trigger_event == "security_finding_automation" or autopilot:
                finding.status = "fixed"
            elif finding.status == "open":
                finding.status = "triaging"
        elif run.status == "failed" and finding.status == "triaging":
            finding.status = "open"  # re-open so it can be retried

        finding.source_run_id = str(run.id)
        finding.updated_at = _now()
        db.commit()
        log.info(
            "security_finding.run_feedback",
            finding_id=finding_id_str,
            run_id=str(run.id),
            run_status=run.status,
            new_finding_status=finding.status,
        )
    except Exception as exc:
        log.warning("security_finding.run_feedback_failed", run_id=str(run.id), error=str(exc))
        try:
            from app.core.config import settings
            if settings.sentry_dsn:
                import sentry_sdk
                sentry_sdk.capture_exception(exc)
        except Exception:
            pass

def execute_run(run_id: str):
    """
    Entry point called by the worker.
    Loads the run, executes the DAG, writes events throughout.

    Supports resuming paused runs: blocks whose output is already in state
    are skipped (their previous output is preserved).
    """
    db = SessionLocal()
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            log.error("run.not_found", run_id=run_id)
            return

        from sqlalchemy.orm import joinedload
        version = db.query(WorkflowVersion).options(
            joinedload(WorkflowVersion.workflow)
        ).filter(
            WorkflowVersion.id == run.workflow_version_id
        ).first()

        run.status = "running"
        run.started_at = run.started_at or _now()
        run.locked_at = _now()
        run.locked_by = f"{socket.gethostname()}:{os.getpid()}"
        run.attempt_count = (run.attempt_count or 0) + 1
        db.commit()
        _emit(db, run_id, None, "run_started", {"node_count": len((version.graph or {}).get("nodes", []))})

        # Accumulated state — includes previous run segment outputs on resume
        state: dict[str, Any] = dict(run.state or {})

        env_id = version.workflow.environment_id
        workspace_id_str = version.workflow.workspace_id

        # Load credentials and egress allowlist from the workflow's environment
        allowed_hosts: list[str] | None = None
        from app.models.environment import Environment as _Env
        if env_id:
            env_row = db.query(_Env).filter(_Env.id == env_id).first()
            if env_row:
                allowed_hosts = env_row.allowed_hosts or None
            cred_rows = db.query(Integration).filter(
                Integration.workspace_id == workspace_id_str,
                Integration.environment_id == env_id,
            ).all()
        else:
            # No environment assigned — load from Default so tool blocks have credentials
            default_env = db.query(_Env).filter(
                _Env.workspace_id == workspace_id_str,
                _Env.name == "Default",
            ).first()
            if default_env:
                allowed_hosts = default_env.allowed_hosts or None
                cred_rows = db.query(Integration).filter(
                    Integration.workspace_id == workspace_id_str,
                    Integration.environment_id == default_env.id,
                ).all()
            else:
                cred_rows = []

        _raw_creds: dict[str, Any] = {
            row.handle: decrypt(row.encrypted_credentials)
            for row in cred_rows
            if row.encrypted_credentials
        }

        # Fallback: merge in any missing handles from the Default environment
        # so integrations connected globally are always available
        if env_id:
            default_env = db.query(_Env).filter(
                _Env.workspace_id == workspace_id_str,
                _Env.name == "Default",
            ).first()
            if default_env and str(default_env.id) != str(env_id):
                fallback_rows = db.query(Integration).filter(
                    Integration.workspace_id == workspace_id_str,
                    Integration.environment_id == default_env.id,
                ).all()
                for row in fallback_rows:
                    if row.handle not in _raw_creds and row.encrypted_credentials:
                        _raw_creds[row.handle] = decrypt(row.encrypted_credentials)

        # Wrap in CredentialStore so accidental repr()/str() calls (e.g. in log lines
        # or Sentry breadcrumbs) never expose plaintext secret values.
        credentials = CredentialStore(_raw_creds)
        del _raw_creds  # drop the plain dict reference immediately

        final_state = _execute_dag(
            run=run,
            version=version,
            initial_state=state,
            db=db,
            credentials=credentials,
            allowed_hosts=allowed_hosts,
            workspace_id_str=str(workspace_id_str),
        )
        _emit_run_analytics(run, version, final_state, db, outcome=run.status, error="")
        _enqueue_online_eval(str(run.id))
        _feedback_to_security_finding(run, db)

    except Exception as e:
        log.exception("run.executor_crash", run_id=run_id)
        if settings.sentry_dsn:
            import sentry_sdk
            with sentry_sdk.push_scope() as scope:
                scope.set_tag("run_id", str(run_id))
                sentry_sdk.capture_exception(e)
        try:
            run = db.query(Run).filter(Run.id == run_id).first()
            if run:
                run.status = "failed"
                run.completed_at = _now()
                run.locked_at = None
                run.locked_by = None
                db.commit()
                _emit_run_analytics(run, None, {}, db, outcome="failed", error=str(e))
                _enqueue_online_eval(str(run.id))
        except Exception:
            pass
    finally:
        db.close()
