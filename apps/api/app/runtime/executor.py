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
import structlog
from collections import defaultdict, deque
from datetime import datetime, timezone
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
    "incident_responder":     ("incident_investigated",  [],           False),
    "postmortem_drafter":     ("postmortem_drafted",     ["issue_url"], True),
    "dependency_updater":     ("dependency_updated",     ["pr_url"],   True),
    "security_patch_updater": ("security_patch_applied", ["pr_url"],   True),
    "docs_drift_detector":    ("docs_updated",           ["issue_url"], True),
    "terraform_reviewer":     ("terraform_reviewed",     [],           False),
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
        def replace(m):
            parts = m.group(1).split(".")
            obj = state.get(parts[0], {})
            for p in parts[1:]:
                if isinstance(obj, dict):
                    obj = obj.get(p, m.group(0))
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


def _classify_failure(exc: Exception, block_id: str | None = None) -> dict[str, Any]:
    """Normalize runtime failures into a structured, user-actionable summary."""
    msg = str(exc)

    code = "EXECUTION_ERROR"
    category = "runtime"
    stop_reason = "exception"
    next_action = "Inspect the failed block output and rerun after fixing the underlying error."

    if isinstance(exc, PermissionError):
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
) -> dict:
    if state.get("__dry_run"):
        return {
            "dry_run": True,
            "note": "Dry run — Brain block would invoke Claude AI with the workflow context",
            "description": block["data"].get("description", ""),
            "is_agentic": block["data"].get("isAgentic", False),
            "remote_host": bool((block.get("data", {}).get("config") or {}).get("remote_host")),
        }

    artifact = compiled_artifacts.get(block["id"], {})
    system_prompt = artifact.get("system_prompt", block["data"].get("description", ""))

    # prompt_file overrides inline description when present
    prompt_file = (block["data"].get("config") or {}).get("prompt_file") or block["data"].get("prompt_file")
    if prompt_file:
        import pathlib
        base = pathlib.Path(__file__).parent.parent.parent  # repo root
        candidate = (base / prompt_file).resolve()
        try:
            candidate.relative_to(base.resolve())  # prevent path traversal
            system_prompt = candidate.read_text(encoding="utf-8")
        except (ValueError, FileNotFoundError, OSError) as exc:
            log.warning("brain.prompt_file_unreadable", path=str(prompt_file), error=str(exc))

    custom = block["data"].get("custom_instructions", "") or ""
    if custom.strip():
        system_prompt = f"{system_prompt}\n\nAdditional instructions:\n{custom.strip()}"
    is_agentic = block["data"].get("isAgentic", False)

    # Model selection via router
    routing_pref = block["data"].get("routingPreference") or "balanced"
    explicit_model = block["data"].get("model") or None
    explicit_provider = block["data"].get("provider") or None
    provider, model_id, routing_reason = _router_resolve(playbook_slug, routing_pref, explicit_model, explicit_provider)
    log.debug("brain.model_selected", block_id=block["id"], provider=provider, model=model_id, reason=routing_reason)

    # Resolve remote host (if the YAML's `runs_on:` was set on this block).
    # When set, all four Brain tools dispatch over SSH to that host rather
    # than running locally on the worker or in Modal.
    remote_host = _resolve_remote_host(block, state, credentials or {})

    from app.runtime.sandbox_session import create_session as _create_session
    session = _create_session(remote_host, credentials)
    _session_closed = False

    def _close_session():
        nonlocal _session_closed
        if not _session_closed:
            _session_closed = True
            try:
                session.close()
            except Exception:
                pass

    def _dispatch_with_creds(tool_name: str, tool_input: dict) -> str:
        # Swap credential placeholders for real values in subprocess env only.
        # Placeholders appear in tool_input (logged to DB); real values never do.
        if tool_name == "run_shell" and cred_env:
            merged_env = {**cred_env, **tool_input.get("env", {})}
            resolved_env = {k: _cred_real.get(v, v) for k, v in merged_env.items()}
            tool_input = {**tool_input, "env": resolved_env}
        return session.dispatch(tool_name, tool_input)

    context = json.dumps({k: v for k, v in state.items() if not k.startswith("__")}, default=str)[:4000]

    # Credential placeholder pattern: model and DB see placeholder tokens, never raw secrets.
    # Real values live only in _cred_real and are swapped into subprocess env at dispatch time.
    cred_env: dict[str, str] = {}   # placeholder values — safe to log / send to LLM
    _cred_real: dict[str, str] = {}  # placeholder → real value — never leaves this function
    cred_names: list[str] = []
    _ENV_NAME_MAP = {
        ("git", "token"): "GIT_TOKEN", ("git", "provider"): "GIT_PROVIDER",
        ("github", "token"): "GIT_TOKEN", ("github", "api_key"): "GIT_TOKEN",
        ("slack", "token"): "SLACK_BOT_TOKEN",
        ("slack", "signing_secret"): "SLACK_SIGNING_SECRET",
        ("linear", "api_key"): "LINEAR_API_KEY",
        ("digitalocean", "token"): "DIGITALOCEAN_TOKEN",
        ("vercel", "token"): "VERCEL_TOKEN",
        ("anthropic", "api_key"): "ANTHROPIC_API_KEY",
        ("modal", "token_id"): "MODAL_TOKEN_ID",
        ("modal", "token_secret"): "MODAL_TOKEN_SECRET",
        ("email", "resend_api_key"): "RESEND_API_KEY",
    }
    for handle, creds in (credentials or {}).items():
        if isinstance(creds, dict):
            for field, val in creds.items():
                if val and isinstance(val, str):
                    env_name = _ENV_NAME_MAP.get((handle, field), f"{handle.upper()}_{field.upper()}")
                    placeholder = f"__CREDENTIAL_{env_name}__"
                    cred_env[env_name] = placeholder
                    _cred_real[placeholder] = val
                    cred_names.append(env_name)
    cred_section = (
        "\n\nCredentials are pre-exported into every run_shell call — use them directly without any setup:\n"
        + "\n".join(f"  ${n}" for n in cred_names)
        + "\nDO NOT check if these vars exist. DO NOT try to read them from files. They are already in the shell environment."
    ) if cred_names else ""

    user_message = f"Workflow context so far:\n{context}{cred_section}\n\nExecute your task."

    sufficiency_instruction = (
        "IMPORTANT: Before doing any work, assess whether you have enough information "
        "to complete this task. If the description is vague, missing critical details, "
        "or you cannot determine what success looks like — respond immediately with:\n"
        "NEEDS_CLARIFICATION: <concise explanation of what is missing>\n"
        "Do not attempt partial work or use any tools if the task is unclear."
    )

    environment_preamble = (
        "EXECUTION ENVIRONMENT:\n"
        "You are running inside a PERSISTENT session — files and directories you create in one\n"
        "run_shell call ARE available in subsequent calls within this task. Use multiple focused\n"
        "tool calls rather than one giant shell script when it makes the work clearer.\n"
        "Pre-installed: git, python3, pip3, curl, wget, node, npm, unzip.\n"
        "\n"
        "DO NOT waste turns on diagnostics:\n"
        "- Do NOT run: which git, apt-get install anything, find / -name git\n"
        "- Do NOT check if env vars are set (python3 -c 'import os; print(os.environ...)') — they are set\n"
        "- Do NOT run echo $GIT_TOKEN or similar — just use it\n"
        "\n"
        "STANDARD REPO SETUP — recommended approach across multiple calls:\n"
        "  Turn 1: git clone https://$GIT_TOKEN@github.com/<owner>/<repo>.git /tmp/repo\n"
        "  Turn 2: cd /tmp/repo && git config user.email 'bot@conductai.ai' && git checkout -b fix/<slug>\n"
        "  Turn 3+: read/edit files, git add, git commit\n"
        "  Final: git push && open PR via curl or gh CLI\n"
        "\n"
        "Fallback (if git clone fails): use python3 urllib to GET/PATCH/PUT via GitHub API.\n"
        "Do NOT switch between approaches mid-task."
    )

    # BYO key: workspace credential (handle or flat env_var) → platform default
    _env_vars = (credentials or {}).get("env_vars") or {}
    _anthropic_key = (
        (credentials or {}).get("anthropic", {}).get("api_key")
        or _env_vars.get("anthropic_api_key")
        or _env_vars.get("ANTHROPIC_API_KEY")
        or settings.anthropic_api_key
    )
    _openai_key = (
        (credentials or {}).get("openai", {}).get("api_key")
        or _env_vars.get("openai_api_key")
        or _env_vars.get("OPENAI_API_KEY")
        or settings.openai_api_key
    )
    _perplexity_key = (
        (credentials or {}).get("perplexity", {}).get("api_key")
        or _env_vars.get("perplexity_api_key")
        or _env_vars.get("PERPLEXITY_API_KEY")
    )

    pricing_snapshot = freeze_pricing_snapshot()

    # Provider fallback keeps existing Anthropic behavior if OpenAI is selected
    # but no key is configured for this workspace/run.
    if provider == "perplexity" and _perplexity_key:
        llm = PerplexityClient(api_key=_perplexity_key, pricing_snapshot=pricing_snapshot)
    elif provider == "openai" and _openai_key:
        llm = OpenAIClient(api_key=_openai_key, pricing_snapshot=pricing_snapshot)
    else:
        if provider == "openai" and not _openai_key:
            log.warning("brain.provider_fallback", reason="missing_openai_key", selected_provider=provider, fallback_provider="anthropic")
            provider, model_id, fallback_reason = _router_resolve(playbook_slug, routing_pref, None, "anthropic")
            routing_reason = f"{routing_reason}; fallback: {fallback_reason}"
        elif provider == "perplexity" and not _perplexity_key:
            log.warning("brain.provider_fallback", reason="missing_perplexity_key", selected_provider=provider, fallback_provider="anthropic")
            provider, model_id, fallback_reason = _router_resolve(playbook_slug, routing_pref, None, "anthropic")
            routing_reason = f"{routing_reason}; fallback: {fallback_reason}"
        llm = AnthropicClient(api_key=_anthropic_key, pricing_snapshot=pricing_snapshot)

    pricing_rates, pricing_version = get_model_rates(provider, model_id, pricing_snapshot)

    if is_agentic:
        # Bounded agentic loop — deterministic retry boundaries from run state
        messages: list[dict] = [{"role": "user", "content": user_message}]
        turns = 0
        max_turns = int(state.get("__max_turns", 20))
        max_turns = max(1, max_turns)
        max_cost_usd = float(state.get("__max_cost_usd", 5.0) or 5.0)
        max_cost_usd = max(0.01, max_cost_usd)
        total_input_tokens = 0
        total_output_tokens = 0
        total_cache_read_tokens = 0
        total_cache_write_tokens = 0
        total_cost_usd = 0.0
        full_system = f"{environment_preamble}\n\n{system_prompt}\n\n{sufficiency_instruction}"

        while turns < max_turns:
            # Trace: user turn
            if db and run_id and block_id:
                turn_msg = messages[-1] if messages else {}
                user_content = turn_msg.get("content", "") if isinstance(turn_msg.get("content"), str) else ""
                _write_trace(db, run_id, block_id, turns + 1, "user",
                             content=user_content[:8000] if user_content else None)

            response = llm.create(
                model=model_id,
                max_tokens=4096,
                system=full_system,
                tools=BRAIN_TOOLS,
                messages=messages,
                cache_system=True,
            )
            turns += 1
            total_input_tokens       += response.usage.input_tokens
            total_output_tokens      += response.usage.output_tokens
            total_cache_read_tokens  += response.usage.cache_read_tokens
            total_cache_write_tokens += response.usage.cache_write_tokens
            total_cost_usd           += response.cost_usd

            if total_cost_usd >= max_cost_usd:
                cost_usd = round(total_cost_usd, 6)
                files_changed, diff_stat = session.capture_artifacts()
                if db and run_id:
                    _emit(db, run_id, block_id, "brain_budget_exhausted", {
                        "reason": "max_cost_reached",
                        "stop_reason": "max_cost_reached",
                        "turns": turns,
                        "max_turns": max_turns,
                        "max_cost_usd": max_cost_usd,
                        "input_tokens": total_input_tokens,
                        "output_tokens": total_output_tokens,
                        "cache_read_tokens": total_cache_read_tokens,
                        "cache_write_tokens": total_cache_write_tokens,
                        "cost_usd": cost_usd,
                        "files_changed": files_changed,
                        "diff_stat": diff_stat,
                        "provider": provider,
                        "model": model_id,
                        "pricing_version": pricing_version,
                        "pricing_rates": pricing_rates,
                        "next_action": "Reduce scope or raise max_cost_usd before retrying.",
                    })
                _close_session()
                raise RuntimeError(
                    f"Cost budget exhausted: agent reached ${cost_usd:.4f} with cap ${max_cost_usd:.4f} "
                    f"after {turns} turns"
                )

            # Collect tool calls from response
            tool_calls  = [b for b in response.content if isinstance(b, LLMToolUseBlock)]
            text_blocks = [b for b in response.content if isinstance(b, LLMTextBlock)]
            final_text  = " ".join(b.text for b in text_blocks)

            # Trace: assistant response
            if db and run_id and block_id:
                _write_trace(db, run_id, block_id, turns, "assistant",
                             content=final_text[:8000] if final_text else None,
                             input_tokens=response.usage.input_tokens,
                             output_tokens=response.usage.output_tokens)

            # First-turn sufficiency check — fail fast before any tools are used
            if turns == 1 and final_text.strip().startswith("NEEDS_CLARIFICATION:"):
                _close_session()
                raise ValueError(final_text.strip())

            if response.stop_reason == "end_turn" or not tool_calls:
                cost_usd = round(total_cost_usd, 6)
                files_changed, diff_stat = session.capture_artifacts()
                if db and run_id:
                    from app.runtime.sandbox import _modal_available
                    if _modal_available():
                        _emit(db, run_id, block_id, "brain_tool_call", {
                            "tool": "modal_lifecycle",
                            "summary": "--- Cleaning Modal Assets ---",
                            "turn": turns,
                        })
                result = {
                    "output": final_text,
                    "turns": turns,
                    "input_tokens": total_input_tokens,
                    "output_tokens": total_output_tokens,
                    "cache_read_tokens": total_cache_read_tokens,
                    "cache_write_tokens": total_cache_write_tokens,
                    "cost_usd": cost_usd,
                    "files_changed": files_changed,
                    "diff_stat": diff_stat,
                    "remote_host_ip": remote_host.get("ip") if remote_host else None,
                    "provider": provider,
                    "model": model_id,
                    "routing_reason": routing_reason,
                    "pricing_version": pricing_version,
                    "pricing_rates": pricing_rates,
                }
                # Extract structured values from the last JSON line of the output
                # so brain blocks can surface keys like pr_url, passed, etc. as
                # direct refs (e.g. {{push_pr.pr_url}}).
                import json as _json
                _output_text = result.get("output", "")
                _last_line = _output_text.strip().rsplit("\n", 1)[-1].strip()
                if _last_line.startswith("{") and _last_line.endswith("}"):
                    try:
                        _extracted = _json.loads(_last_line)
                        if isinstance(_extracted, dict):
                            result.update(_extracted)
                    except Exception:
                        pass
                _close_session()
                return result

            # Append assistant message (provider-specific format via adapter)
            messages.extend(llm.make_assistant_turn(response))

            # Emit Modal lifecycle event on first tool-dispatching turn
            if turns == 1 and db and run_id:
                from app.runtime.sandbox import _modal_available
                if _modal_available():
                    _emit(db, run_id, block_id, "brain_tool_call", {
                        "tool": "modal_lifecycle",
                        "summary": "--- Initializing Modal Assets ---",
                        "turn": 0,
                    })

            # Execute tool calls and collect results
            raw_tool_results: list[tuple[str, str]] = []
            for tc in tool_calls:
                # Trace: tool_use
                if db and run_id and block_id:
                    _write_trace(db, run_id, block_id, turns, "tool_use",
                                 tool_name=tc.name,
                                 tool_input=tc.input or None,
                                 tool_use_id=tc.id)

                try:
                    result_content = _dispatch_with_creds(tc.name, tc.input)
                except RuntimeError as sandbox_err:
                    if db and run_id:
                        _emit(db, run_id, block_id, "brain_tool_call", {
                            "tool": "modal_error",
                            "summary": str(sandbox_err),
                            "turn": turns,
                        })
                    raise
                raw_tool_results.append((tc.id, result_content))

                # Trace: tool_result
                if db and run_id and block_id:
                    _write_trace(db, run_id, block_id, turns, "tool_result",
                                 content=result_content[:8000] if result_content else None,
                                 tool_use_id=tc.id)
                if db and run_id:
                    _emit(db, run_id, block_id, "brain_tool_call", {
                        "tool": tc.name,
                        "summary": _summarise_tool_call(tc.name, tc.input),
                        "turn": turns,
                    })

            # Append tool results (provider-specific format via adapter)
            messages.extend(llm.make_tool_results_turn(raw_tool_results))

        cost_usd = round(total_cost_usd, 6)
        files_changed, diff_stat = session.capture_artifacts()
        if db and run_id:
            from app.runtime.sandbox import _modal_available
            if _modal_available():
                _emit(db, run_id, block_id, "brain_tool_call", {
                    "tool": "modal_lifecycle",
                    "summary": "--- Cleaning Modal Assets ---",
                    "turn": max_turns,
                })
            _emit(db, run_id, block_id, "brain_budget_exhausted", {
                "reason": "max_turns_reached",
                "stop_reason": "max_turns_reached",
                "turns": max_turns,
                "max_turns": max_turns,
                "max_cost_usd": max_cost_usd,
                "input_tokens": total_input_tokens,
                "output_tokens": total_output_tokens,
                "cache_read_tokens": total_cache_read_tokens,
                "cache_write_tokens": total_cache_write_tokens,
                "cost_usd": cost_usd,
                "files_changed": files_changed,
                "diff_stat": diff_stat,
                "provider": provider,
                "model": model_id,
                "pricing_version": pricing_version,
                "pricing_rates": pricing_rates,
                "next_action": "Reduce scope or increase max_turns before retrying.",
            })
        _close_session()
        raise RuntimeError(
            f"Turn budget exhausted: agent did not reach end_turn after {max_turns} turns "
            f"({total_input_tokens} input / {total_output_tokens} output tokens, ${cost_usd:.4f})"
        )

    else:
        # Single call (no tools)
        response = llm.create(
            model=model_id,
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
            cache_system=True,
        )
        text = next((b.text for b in response.content if isinstance(b, LLMTextBlock)), "")
        if db and run_id and block_id:
            _emit(db, run_id, block_id, "brain_tool_call", {
                "turn": 1,
                "tool": "single_call",
                "summary": text[:300],
                "input": user_message[:600],
                "output": text,
                "model": model_id,
                "provider": provider,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            })
        result = {
            "output": text,
            "turns": 1,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cost_usd": response.cost_usd,
            "provider": provider,
            "model": model_id,
            "routing_reason": routing_reason,
            "pricing_version": pricing_version,
            "pricing_rates": pricing_rates,
        }
        # Extract structured values from the last JSON line of the output
        import json as _json
        _output_text = result.get("output", "")
        _last_line = _output_text.strip().rsplit("\n", 1)[-1].strip()
        if _last_line.startswith("{") and _last_line.endswith("}"):
            try:
                _extracted = _json.loads(_last_line)
                if isinstance(_extracted, dict):
                    result.update(_extracted)
            except Exception:
                pass
        _close_session()
        return result


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
    from app.runtime.integrations import github, slack, linear, digitalocean, vercel, railway, conduct

    dry_run = state.get("__dry_run", False)
    data = block["data"]
    integration = data.get("integration")
    config = data.get("config", {})
    params = _resolve_refs(config.get("params", {}), state)

    if not integration:
        return {"skipped": True, "reason": "No integration configured"}

    action = config.get("action", "")

    if integration == "conduct":
        return conduct.execute(action, params, creds={}, db=db, workspace_id=workspace_id)

    if dry_run:
        creds = credentials.get(integration, {})
        if not creds:
            env_vars = credentials.get("env_vars") or {}
            _FLAT_FALLBACKS_DRY: dict[str, list[str]] = {
                "github": ["GITHUB_TOKEN", "GIT_TOKEN"],
                "slack": ["SLACK_BOT_TOKEN"],
                "linear": ["LINEAR_API_KEY"],
                "digitalocean": ["DIGITALOCEAN_TOKEN", "DO_TOKEN"],
                "vercel": ["VERCEL_TOKEN"],
                "railway": ["RAILWAY_TOKEN"],
            }
            has_flat = any(env_vars.get(k) for k in _FLAT_FALLBACKS_DRY.get(integration, []))
            if not has_flat:
                return {"dry_run": True, "warning": f"No credentials for {integration} — would fail in a real run", "action": action}
        return _dry_run_mock(integration, action, params)

    creds = credentials.get(integration, {})
    if not creds:
        # Fall back to flat env_vars — users store keys like GITHUB_TOKEN, SLACK_BOT_TOKEN
        # as plain key=value pairs rather than under a named integration handle.
        env_vars = credentials.get("env_vars") or {}
        _FLAT_FALLBACKS: dict[str, list[str]] = {
            "github":       ["GITHUB_TOKEN", "GIT_TOKEN"],
            "slack":        ["SLACK_BOT_TOKEN"],
            "linear":       ["LINEAR_API_KEY"],
            "digitalocean": ["DIGITALOCEAN_TOKEN", "DO_TOKEN"],
            "vercel":       ["VERCEL_TOKEN"],
            "railway":      ["RAILWAY_TOKEN"],
        }
        for key in _FLAT_FALLBACKS.get(integration, []):
            val = env_vars.get(key)
            if val:
                creds = {"token": val, "api_key": val}
                break

    if not creds:
        return {"skipped": True, "reason": f"No credentials for {integration}"}

    target_host = _INTEGRATION_HOSTS.get(integration)
    if target_host:
        _check_egress(target_host, allowed_hosts)

    if integration == "github":
        return github.execute(action, params, creds)
    if integration == "slack":
        return slack.execute(action, params, creds)
    if integration == "linear":
        return linear.execute(action, params, creds)
    if integration == "digitalocean":
        return digitalocean.execute(action, params, creds)
    if integration == "vercel":
        return vercel.execute(action, params, creds)
    if integration == "railway":
        return railway.execute(action, params, creds)

    return {"skipped": True, "reason": f"Integration '{integration}' not yet implemented"}


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
    from app.runtime.integrations import slack, email as email_integration
    from app.core.config import settings

    dry_run = state.get("__dry_run", False)
    data = block["data"]
    integration = data.get("integration", "slack")
    config = data.get("config", {})

    if dry_run:
        summary = _build_run_summary(state)
        return {"dry_run": True, "integration": integration, "preview": summary, "note": f"Dry run — would send via {integration}"}

    results: dict = {}

    send_slack = integration in ("slack", "both")
    send_email = integration in ("email", "both")

    if send_slack:
        slack_creds = credentials.get("slack", {})
        channel = _resolve_refs(config.get("channel", "#general"), state)
        if not slack_creds:
            results["slack"] = {"sent": False, "reason": "No Slack credentials configured"}
        elif not channel:
            results["slack"] = {"sent": False, "reason": "No Slack channel configured"}
        else:
            try:
                _, body = _fill_template(_load_template("slack_output.txt"), state, workflow_name, trace_url)
                use_approval = config.get("approval", False) and bool(run_id)
                if use_approval:
                    r = slack.execute("post_approval_message", {
                        "channel": channel,
                        "text": body,
                        "run_id": run_id,
                        "callback_url": trace_url,
                    }, slack_creds)
                else:
                    r = slack.execute("post_message", {"channel": channel, "text": body}, slack_creds)
                results["slack"] = r
            except Exception as e:
                results["slack"] = {"sent": False, "error": str(e)}

    if send_email:
        email_creds = dict(credentials.get("email", credentials.get("resend", {})))
        if not email_creds.get("resend_api_key") and settings.resend_api_key:
            email_creds["resend_api_key"] = settings.resend_api_key
        to = _resolve_refs(config.get("to", ""), state)
        from_address = config.get("from_address") or settings.email_from
        if not email_creds:
            results["email"] = {"sent": False, "reason": "No email credentials configured — add Resend or SendGrid in Settings"}
        elif not to:
            results["email"] = {"sent": False, "reason": "No recipient address configured — set 'Email address' on the output block"}
        else:
            try:
                subject, body = _fill_template(_load_template("email_output.txt"), state, workflow_name, trace_url)
                r = email_integration.execute("send_email", {"to": to, "subject": subject, "body": body, "from_address": from_address}, email_creds)
                results["email"] = r
            except Exception as e:
                results["email"] = {"sent": False, "error": str(e)}

    if integration == "webhook":
        import hashlib
        import hmac as hmac_lib
        import urllib.request
        webhook_url = _resolve_refs(config.get("webhook_url", ""), state)
        webhook_secret = config.get("webhook_secret", "")
        if not webhook_url:
            return {"sent": False, "reason": "No webhook URL configured"}
        payload = json.dumps({
            "workflow": workflow_name,
            "trace_url": trace_url,
            "state": {k: v for k, v in state.items() if not k.startswith("__")},
        }, default=str).encode()
        headers = {"Content-Type": "application/json", "User-Agent": "ConductAI/1.0"}
        if webhook_secret:
            sig = hmac_lib.new(webhook_secret.encode(), payload, hashlib.sha256).hexdigest()
            headers["X-ConductAI-Signature"] = f"sha256={sig}"
        try:
            req = urllib.request.Request(webhook_url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                return {"sent": True, "integration": "webhook", "status_code": resp.status}
        except Exception as e:
            return {"sent": False, "integration": "webhook", "error": str(e)}

    if not results:
        return {"sent": False, "reason": "No integration configured"}

    return {"sent": True, "integration": integration, **results}


def _evaluate_condition_jinja(raw: str, state: dict) -> str | None:
    """
    Try evaluating a Jinja2 condition expression against the state.
    Returns the rendered string ('True'/'False'/etc.) or None on failure.
    Handles expressions like {{triage.is_real == false}} and
    {{_trigger.severity == 'critical' or _trigger.severity == 'high'}}.
    """
    try:
        import jinja2
        env = jinja2.Environment(undefined=jinja2.Undefined)
        rendered = env.from_string(raw).render(**state).strip()
        # If the template contained no Jinja2 tags, rendered == raw — skip
        if rendered == raw:
            return None
        return rendered
    except Exception:
        return None


def _execute_logic(block: dict, state: dict) -> dict:
    """
    Evaluate a condition and return route: 'pass' or 'fail'.

    Checks (in order):
    1. Explicit condition expression in block config
       - Jinja2 evaluation: {{triage.is_real == false}} → 'True'/'False'
       - Equality expression: "value == true/false" evaluated directly
       - Keyword-based: pass/success/true -> pass; fail/error/false -> fail
    2. exit_code == 0 from last shell output
    3. Keywords 'pass', 'success', 'true', '0' in last output
    """
    config = block["data"].get("config", {})
    raw_condition = config.get("condition", "")
    # Try Jinja2 evaluation first (handles {{expr == value}} patterns)
    jinja_result = _evaluate_condition_jinja(raw_condition, state)
    if jinja_result is not None:
        r = jinja_result.strip().lower()
        if r in ("true", "1", "yes", "pass", "success"):
            return {"route": "pass", "condition": raw_condition, "evaluated_on": jinja_result}
        if r in ("false", "0", "no", "fail", "error"):
            return {"route": "fail", "condition": raw_condition, "evaluated_on": jinja_result}
    condition_expr = _resolve_refs(raw_condition, state)
    last_output = str(state.get("__last_output", "")).lower()

    # If config has an explicit condition expression, evaluate it
    if condition_expr:
        cond_stripped = condition_expr.strip()
        cond_lower = cond_stripped.lower()

        # Handle equality expressions: "<value> == true/false" or "<value> == <value>"
        eq_match = re.match(r"^(.+?)\s*==\s*(.+)$", cond_stripped, re.IGNORECASE)
        if eq_match:
            lhs = eq_match.group(1).strip().lower()
            rhs = eq_match.group(2).strip().lower()
            # Normalise Python/JSON booleans
            lhs_val = lhs in ("true", "1", "yes")  if lhs in ("true", "false", "1", "0", "yes", "no") else lhs
            rhs_val = rhs in ("true", "1", "yes") if rhs in ("true", "false", "1", "0", "yes", "no") else rhs
            matched = lhs_val == rhs_val
            route = "pass" if matched else "fail"
            return {"route": route, "condition": condition_expr, "evaluated_on": f"{lhs} == {rhs}"}

        # Keyword-only expressions
        if any(k in cond_lower for k in ("fail", "error")):
            return {"route": "fail", "condition": condition_expr, "evaluated_on": last_output[:200]}
        if cond_lower in ("true", "pass", "success"):
            return {"route": "pass", "condition": condition_expr, "evaluated_on": cond_lower}
        if cond_lower in ("false",):
            return {"route": "fail", "condition": condition_expr, "evaluated_on": cond_lower}

    # Check exit_code in last output (JSON blob from run_shell)
    try:
        last_json = json.loads(state.get("__last_output", "{}"))
        if isinstance(last_json, dict):
            exit_code = last_json.get("exit_code")
            if exit_code is not None:
                route = "pass" if int(exit_code) == 0 else "fail"
                return {"route": route, "condition": condition_expr, "exit_code": exit_code}
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    # Keyword match on last output string
    if any(k in last_output for k in ("pass", "success", "true", "all tests passed", "exit code 0")):
        return {"route": "pass", "condition": condition_expr, "evaluated_on": last_output[:200]}
    if any(k in last_output for k in ("fail", "error", "false", "exception", "traceback")):
        return {"route": "fail", "condition": condition_expr, "evaluated_on": last_output[:200]}

    # Default: fail (fail-closed — ambiguous output is not a success signal)
    return {"route": "fail", "condition": condition_expr, "evaluated_on": last_output[:200]}


def _execute_approval(block: dict, state: dict, credentials: dict, run_id: str) -> dict:
    """
    Pause the run and send a Slack DM with Approve/Reject buttons.
    Raises ApprovalRequired so the executor can pause the run.

    On resume, the executor injects __approval_{block_id} = 'approved'|'rejected'
    into state before re-queuing, so the block returns without raising.
    """
    from app.runtime.integrations import slack

    block_id = block["id"]
    approval_key = f"__approval_{block_id}"

    # Resuming — decision already recorded by the approval webhook
    if approval_key in state:
        decision = state[approval_key]
        if decision == "rejected":
            raise ValueError(f"Approval rejected for block {block_id}")
        return {"decision": "approved", "resumed": True}

    # First encounter — send Slack/email/both notification and pause
    data = block["data"]
    config = data.get("config", {})
    message = _resolve_refs(
        config.get("message", data.get("description", "Approval required to continue.")),
        state,
    )
    via = config.get("via", "slack")
    slack_user = config.get("slack_user")
    channel = config.get("channel", "#general")
    approval_email = config.get("approval_email")
    callback_url = f"{settings.api_base_url}/runs/{run_id}/approve"

    # ── Slack ──────────────────────────────────────────────────────────────────
    if via in ("slack", "both"):
        slack_creds = credentials.get("slack", {})
        if slack_creds:
            try:
                slack.execute(
                    "post_approval_message",
                    {
                        "channel": slack_user or channel,
                        "text": message,
                        "run_id": run_id,
                        "callback_url": callback_url,
                    },
                    slack_creds,
                )
            except Exception as e:
                log.warning("approval.slack_failed", error=str(e))

    # ── Email ──────────────────────────────────────────────────────────────────
    if via in ("email", "both") and approval_email:
        try:
            from app.runtime.integrations import email as email_int
            approve_url = f"{callback_url}?run_id={run_id}&decision=approved"
            reject_url  = f"{callback_url}?run_id={run_id}&decision=rejected"
            email_body = (
                f"{message}\n\n"
                f"Approve: {approve_url}\n"
                f"Reject:  {reject_url}\n"
            )
            email_creds = credentials.get("email", credentials.get("resend", {}))
            email_int.execute(
                "send",
                {
                    "to": approval_email,
                    "subject": f"Approval required — run {run_id[:8]}",
                    "body": email_body,
                },
                email_creds,
            )
        except Exception as e:
            log.warning("approval.email_failed", error=str(e))

    raise ApprovalRequired(block_id, message)


def _execute_guard(block: dict, state: dict, workspace_id: str, db) -> dict:
    """Apply ConductGuard policy check at this point in the workflow.

    Evaluates all active team policies against the current workflow state.
    Violations are handled per enforcement_mode:
      block  — raises RuntimeError, halts the run
      warn   — records audit event, adds warning to output, run continues
      audit  — records audit event silently, run continues

    Config keys:
      enforcement_mode: block | warn | audit  (default: block)
      context_keys: list of state keys to include in pattern matching
                    (default: all state keys)
      rule_ids: list of specific rule IDs to evaluate
                (default: all enabled rules)
    """
    import re as _re
    import uuid as _uuid
    from datetime import datetime, timezone
    from app.modules.guard.models import GuardAuditEvent, GuardPolicy

    config           = block.get("config") or {}
    enforcement_mode = config.get("enforcement_mode", "block")
    context_keys     = config.get("context_keys") or []
    rule_ids_filter  = set(config.get("rule_ids") or [])

    # ── 1. Verify Guard is installed for this workspace ───────────────────────
    try:
        ws_uuid = _uuid.UUID(workspace_id)
    except ValueError:
        ws_uuid = None

    guard_installed = False
    if ws_uuid:
        from sqlalchemy import text as _text
        guard_installed = db.execute(
            _text("SELECT 1 FROM guard_config WHERE workspace_id = :ws LIMIT 1"),
            {"ws": str(ws_uuid)},
        ).fetchone() is not None

    if not guard_installed:
        if enforcement_mode == "block":
            raise RuntimeError(
                "Guard block: ConductGuard is not installed for this workspace. "
                "Install Guard in Settings → Modules to use this block."
            )
        return {
            "status": "skipped",
            "reason": "guard_not_installed",
            "enforcement_mode": enforcement_mode,
        }

    # ── 2. Build context string from workflow state ────────────────────────────
    if context_keys:
        context_dict = {k: state.get(k) for k in context_keys if k in state}
    else:
        # Exclude internal keys starting with __
        context_dict = {k: v for k, v in state.items() if not k.startswith("__")}

    context_json = json.dumps(context_dict, default=str)

    # Extract path-like values for match_path_pattern
    path_values = []
    def _collect_paths(obj):
        if isinstance(obj, str) and ("/" in obj or "\\" in obj):
            path_values.append(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _collect_paths(v)
        elif isinstance(obj, list):
            for v in obj:
                _collect_paths(v)
    _collect_paths(context_dict)
    path_text = " ".join(path_values)

    # ── 3. Load active policies ───────────────────────────────────────────────
    policy_q = db.query(GuardPolicy).filter(
        GuardPolicy.workspace_id == ws_uuid,
        GuardPolicy.enabled.is_(True),
    )
    if rule_ids_filter:
        policy_q = policy_q.filter(GuardPolicy.rule_id.in_(rule_ids_filter))
    policies = policy_q.order_by(GuardPolicy.updated_at.desc()).all()

    # ── 4. Evaluate rules ─────────────────────────────────────────────────────
    violations = []
    for policy in policies:
        # match_tool — for workflow context use "workflow" as the synthetic tool
        match_tool = (policy.match_tool or "*").lower()
        if match_tool != "*":
            allowed = {t.strip() for t in match_tool.split(",")}
            if "workflow" not in allowed:
                continue

        # match_pattern — search context JSON
        if policy.match_pattern:
            try:
                if not _re.search(policy.match_pattern, context_json, _re.IGNORECASE):
                    continue
            except _re.error:
                continue

        # match_path_pattern — search path-like values
        if policy.match_path_pattern:
            try:
                if not _re.search(policy.match_path_pattern, path_text, _re.IGNORECASE):
                    continue
            except _re.error:
                continue

        violations.append(policy)

    # ── 5. Handle violations ──────────────────────────────────────────────────
    block_id   = block.get("id", "guard")
    now        = datetime.now(timezone.utc)
    warnings   = []

    def _record_event(policy: GuardPolicy, decision: str):
        try:
            db.add(GuardAuditEvent(
                workspace_id=ws_uuid,
                ai_tool="workflow",
                tool_call=block_id,
                input_summary=context_json[:500],
                decision=decision,
                rule_id=policy.rule_id,
                rule_message=policy.message,
                ts=now,
            ))
            db.flush()
        except Exception:
            pass

    for v in violations:
        message = v.message or f"Policy violation: {v.rule_id}"
        action  = v.action

        if action == "block":
            _record_event(v, "blocked")
            db.commit()
            raise RuntimeError(f"[ConductGuard] Blocked by policy '{v.rule_id}': {message}")

        elif action in ("warn", "approval"):
            _record_event(v, "warned")
            warnings.append({"rule_id": v.rule_id, "message": message})

        else:  # audit
            _record_event(v, "audited")

    if warnings or violations:
        db.commit()

    return {
        "status": "passed",
        "workspace_id": str(ws_uuid),
        "enforcement_mode": enforcement_mode,
        "rules_checked": len(policies),
        "violations": len(violations),
        "warnings": warnings,
    }


# ── main executor ─────────────────────────────────────────────────────────────

def _execute_memory(block: dict, state: dict, db, run_id: str, workspace_id: str, playbook_slug: str, credentials: dict | None = None) -> dict:
    """
    Read or write agent memory with vector similarity search.

    read:  queries agent_memory for the most similar past summaries, returns them
           as `entries` list so the brain block can use prior context.
    write: embeds the resolved summary and inserts a new row.
    """
    try:
        return _execute_memory_inner(block, state, db, run_id, workspace_id, playbook_slug, credentials)
    except Exception as e:
        log.warning("memory.block_failed", error=str(e), run_id=run_id)
        try:
            db.rollback()
        except Exception:
            pass
        action = (block.get("data", {}).get("config", {}) or {}).get("action", "read")
        if action == "write":
            return {"written": False, "note": f"memory error: {e}"}
        return {"entries": [], "note": f"memory error: {e}"}


def _execute_memory_inner(block: dict, state: dict, db, run_id: str, workspace_id: str, playbook_slug: str, credentials: dict | None = None) -> dict:
    from app.models.agent_memory import AgentMemory
    from app.runtime.embedding_client import create_embedding_client

    data = block["data"]
    config = data.get("config", {})
    action = config.get("action", "read")
    scope = config.get("scope", "repo")
    key = _resolve_refs(config.get("key", ""), state)
    creds = credentials or {}
    # Flat env vars are stored under the "env_vars" handle with lowercased keys
    env_vars = creds.get("env_vars") or {}
    client = create_embedding_client(
        openai_api_key=(
            creds.get("openai", {}).get("api_key")
            or env_vars.get("openai_api_key")
            or env_vars.get("OPENAI_API_KEY")
        ),
        voyage_api_key=(
            creds.get("voyage", {}).get("api_key")
            or env_vars.get("voyage_api_key")
            or env_vars.get("VOYAGE_API_KEY")
        ),
    )

    if action == "read":
        limit = int(config.get("limit", 5))
        if not key:
            return {"entries": [], "note": "No key resolved"}

        if client:
            # Guard: column is vector(1536); Voyage is 512d and not yet supported natively.
            if client.dimensions != 1536:
                log.warning("memory.dimension_mismatch", client_dims=client.dimensions, column_dims=1536)
                client = None

        if client:
            query_vec = client.embed(key)
            # Native vector column — no ::vector cast needed; HNSW index kicks in automatically.
            rows = db.execute(
                __import__("sqlalchemy").text("""
                    SELECT summary, created_at,
                           (embedding <=> CAST(:vec AS vector)) AS distance
                    FROM agent_memory
                    WHERE workspace_id = :ws
                      AND playbook_slug = :slug
                      AND scope = :scope
                      AND key = :key
                      AND embedding IS NOT NULL
                    ORDER BY distance ASC
                    LIMIT :lim
                """),
                {
                    "vec": str(query_vec),
                    "ws": workspace_id,
                    "slug": playbook_slug,
                    "scope": scope,
                    "key": key,
                    "lim": limit,
                },
            ).fetchall()
        else:
            # No embedding provider (or dimension mismatch) — fall back to recency.
            rows = db.query(AgentMemory).filter(
                AgentMemory.workspace_id == workspace_id,
                AgentMemory.playbook_slug == playbook_slug,
                AgentMemory.scope == scope,
                AgentMemory.key == key,
            ).order_by(AgentMemory.created_at.desc()).limit(limit).all()

        entries = [{"summary": r.summary, "at": str(r.created_at)} for r in rows]
        return {"entries": entries, "count": len(entries), "scope": scope, "key": key}

    elif action == "write":
        summary_tpl = config.get("summary", "")
        summary = _resolve_refs(summary_tpl, state).strip()
        if not summary:
            return {"written": False, "note": "Empty summary — nothing written"}

        # Guard dimension mismatch same as read path.
        if client and client.dimensions != 1536:
            log.warning("memory.dimension_mismatch", client_dims=client.dimensions, column_dims=1536)
            client = None

        embedding_vec: list[float] | None = None
        if client:
            try:
                embedding_vec = client.embed(summary)
            except Exception as e:
                log.warning("memory.embed_failed", error=str(e))

        row = AgentMemory(
            workspace_id=workspace_id,
            playbook_slug=playbook_slug,
            scope=scope,
            key=key,
            summary=summary,
            embedding=embedding_vec,
            run_id=run_id if run_id else None,
        )
        db.add(row)
        db.commit()
        return {"written": True, "scope": scope, "key": key, "chars": len(summary)}

    return {"skipped": True, "note": f"Unknown memory action: {action}"}


def _execute_mcp(block: dict, state: dict, cred_store: object) -> dict:
    """Execute an MCP tool call. Config: credential_key, tool_name, transport, params."""
    from app.runtime.integrations.mcp_client import call_tool

    data   = block.get("data", {})
    config = data.get("config", {}) or {}

    credential_key = config.get("credential_key", "")
    tool_name      = config.get("tool_name", "")
    transport      = config.get("transport", "auto")
    raw_params     = config.get("params", {}) or {}
    params         = _resolve_refs(raw_params, state)

    if not credential_key:
        return {"skipped": True, "reason": "No MCP credential configured"}
    if not tool_name:
        return {"skipped": True, "reason": "No MCP tool configured"}

    # server_url may come from block config (panel-set) or from the credential vault entry
    server_url = config.get("server_url") or None

    creds = cred_store.get(credential_key) if cred_store else {}
    if not creds:
        return {"skipped": True, "reason": f"Credential '{credential_key}' not found"}

    if not server_url:
        server_url = creds.get("server_url") or creds.get("url")
    token = creds.get("token") or creds.get("api_key") or (creds if isinstance(creds, str) else None)

    if not server_url:
        return {"skipped": True, "reason": f"Credential '{credential_key}' missing server_url"}

    if state.get("__dry_run"):
        return {"dry_run": True, "credential_key": credential_key, "tool_name": tool_name, "params": params}

    result = call_tool(server_url, token, tool_name, params, transport=transport)

    if isinstance(result, dict):
        return {"tool": tool_name, **result}
    return {"tool": tool_name, "output": str(result)}


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
    if "inputs" not in state:
        inputs_spec = graph.get("inputs_spec") or {}
        if inputs_spec:
            state["inputs"] = {
                k: (v.get("default") if isinstance(v, dict) else v)
                for k, v in inputs_spec.items()
            }

    failed = False
    fail_error = ""
    fail_summary: dict[str, Any] | None = None
    logic_routes: dict[str, str] = {}  # block_id → 'pass'|'fail'

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

        try:
            if block_type == "trigger":
                # Flatten github_issue fields so {{_trigger.repo_owner}} refs resolve
                result = {"triggered": True}
                if "github_issue" in state:
                    result.update(state["github_issue"])
                    result["github_issue"] = state["github_issue"]
                if "github_trigger" in state:
                    result["github_trigger"] = state["github_trigger"]

            elif block_type == "brain":
                # Auto-guard hook: run guard before every agentic brain block
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
                            raise  # guard blocked — propagate
                        except Exception as _ge:
                            log.warning("guard.auto_hook_failed", block_id=block_id, error=str(_ge))

                slug = getattr(getattr(version, "workflow", None), "playbook_slug", None)
                result = _execute_brain(block, state, compiled, credentials=credentials,
                                        db=db, run_id=run_id, block_id=block_id,
                                        playbook_slug=slug)

            elif block_type == "tool":
                result = _execute_tool(block, state, credentials, allowed_hosts=allowed_hosts, db=db, workspace_id=workspace_id_str)

            elif block_type == "output":
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
                    continue

            elif block_type == "logic":
                result = _execute_logic(block, state)
                logic_routes[block_id] = result.get("route", "pass")
                _logic_routes_version += 1  # invalidate cached skip set

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

            else:
                result = {"status": "skipped", "type": block_type}

            state[block_id] = result
            state["__last_output"] = json.dumps(result, default=str)

            _emit(db, run_id, block_id, "block_completed", {"output": result})

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
