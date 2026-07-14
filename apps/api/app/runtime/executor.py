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
import functools
import structlog
import yaml
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.runtime.llm_client import AnthropicClient, OpenAIClient, PerplexityClient, LLMTextBlock, LLMToolUseBlock
from app.runtime.model_router import resolve as _router_resolve
from app.runtime.pricing import freeze_pricing_snapshot, get_model_rates
from app.core.crypto import decrypt
from app.core.credentials import CredentialStore, get_all_credentials
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


# CredentialStore lives in app.core.credentials — imported above


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
    elif "[ConductGuard] Blocked by policy" in msg:
        # Guard policy fired — this is a governance decision, not a crash.
        # Surface it as such so the UI shows a clean "blocked" state and
        # the user knows where to go to fix it.
        code = "GUARD_POLICY_BLOCKED"
        category = "governance"
        stop_reason = "policy_block"
        # Pull the rule_id out of the message for a more actionable hint
        import re as _re
        m = _re.search(r"policy '([^']+)'", msg)
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


# ── main entry point ──────────────────────────────────────────────────────────

def execute_run(run_id: str):
    """
    Entry point called by the worker.
    Loads the run, executes the DAG, writes events throughout.

    Supports resuming paused runs: blocks whose output is already in state
    are skipped (their previous output is preserved).
    """
    from app.runtime.dag_runner import _execute_dag

    db = SessionLocal()
    _run_token_row_id: str | None = None  # declared before try so finally can reference it
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
        _env_row = db.query(_Env).filter(_Env.id == env_id).first() if env_id else \
                   db.query(_Env).filter(_Env.workspace_id == workspace_id_str, _Env.name == "Default").first()
        if _env_row:
            allowed_hosts = _env_row.allowed_hosts or None
        credentials = get_all_credentials(db, workspace_id_str, environment_id=env_id)

        # Build RunContext — typed contract for this run. Fails fast if required fields missing.
        from app.core.credentials import mint_cred_token as _mint_cred_token
        from app.runtime.run_contract import RunContext as _RunContext
        _cred_handles = list(credentials.keys())
        _cred_token = ""
        if _cred_handles:
            try:
                _cred_token = _mint_cred_token(
                    db, str(run.id), workspace_id_str,
                    allowed_handles=_cred_handles,
                    environment_id=str(env_id) if env_id else None,
                    ttl_seconds=7200,
                )
            except Exception:
                log.warning("run.cred_token_mint_failed", run_id=run_id)

        # Stamp agent_role_id on the run if CONDUCT_AGENT_TOKEN is in credentials.
        _env_vars_creds = credentials.get("env_vars") or {}
        if isinstance(_env_vars_creds, dict) and _env_vars_creds.get("CONDUCT_AGENT_TOKEN"):
            from app.modules.agent_identity.models import AgentIdentity as _AgentIdentity
            _identity = db.query(_AgentIdentity).filter(
                _AgentIdentity.workspace_id == workspace_id_str,
                _AgentIdentity.environment_id == str(env_id or ""),
            ).first()
            if _identity and not run.agent_role_id:
                run.agent_role_id = str(_identity.id)
                db.commit()

        # Read pre-minted agent run token (created at trigger time).
        from app.modules.agent_identity.run_token_model import AgentRunToken as _AgentRunToken
        from app.core.crypto import decrypt as _rt_decrypt
        _conduct_run_token = ""
        _rt = db.query(_AgentRunToken).filter(
            _AgentRunToken.run_id == str(run.id),
            _AgentRunToken.invalidated_at == None,  # noqa: E711
        ).first()
        if _rt:
            _run_token_row_id = _rt.id
            try:
                _plaintext = (_rt_decrypt(_rt.token_encrypted) or {}).get("token") if _rt.token_encrypted else None
                if _plaintext:
                    _conduct_run_token = _plaintext
                    _ev = credentials.get("env_vars") or {}
                    if isinstance(_ev, dict):
                        _ev["CONDUCT_RUN_TOKEN"] = _plaintext
                        credentials._data["env_vars"] = _ev
                    _rt.token_encrypted = None
                    db.commit()
            except Exception:
                pass  # fail-open: run proceeds without short-lived token

        # Construct RunContext — single typed source of truth for all run infrastructure.
        # apply_to_state() writes every field into state so blocks read them unchanged.
        _user_email_ctx = state.get("__user_email") or None
        try:
            _ctx = _RunContext(
                workspace_id=workspace_id_str,
                run_id=str(run.id),
                cred_token=_cred_token,
                cred_api_url=settings.api_base_url,
                cred_handles=_cred_handles,
                conduct_run_token=_conduct_run_token,
                max_turns=int(state.get("__max_turns", 20)),
                max_cost_usd=float(state.get("__max_cost_usd", settings.default_max_cost_usd)),
                user_email=_user_email_ctx,
                env_id=str(env_id) if env_id else None,
            )
            _ctx.apply_to_state(state)
        except ValueError as _ctx_err:
            log.error("run.context_build_failed", run_id=run_id, error=str(_ctx_err))
            raise

        final_state = _execute_dag(
            run=run,
            version=version,
            initial_state=state,
            db=db,
            credentials=None,  # blocks fetch via broker using state["__cred_token__"]
            allowed_hosts=allowed_hosts,
            workspace_id_str=str(workspace_id_str),
            env_id=env_id,
        )
        _emit_run_analytics(run, version, final_state, db, outcome=run.status, error="")
        _enqueue_online_eval(str(run.id))

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
        # Invalidate ephemeral run token so it cannot be replayed after the run ends.
        if _run_token_row_id:
            try:
                from app.modules.agent_identity.run_token_model import AgentRunToken as _AgentRunToken
                from datetime import datetime as _dt, timezone as _rtz
                _inv_db = SessionLocal()
                try:
                    _rt = _inv_db.query(_AgentRunToken).filter(_AgentRunToken.id == _run_token_row_id).first()
                    if _rt and not _rt.invalidated_at:
                        _rt.invalidated_at = _dt.now(_rtz.utc)
                        _inv_db.commit()
                    _cred_tok = state.get("__cred_token__")
                    if _cred_tok:
                        from sqlalchemy import text as _csql
                        _inv_db.execute(_csql(
                            "UPDATE cred_retrieval_tokens SET expires_at = now() WHERE token = :t"
                        ), {"t": _cred_tok})
                        _inv_db.commit()
                finally:
                    _inv_db.close()
            except Exception:
                pass  # never let token cleanup crash the run
        db.close()


# ── Re-exports for backward compatibility (tests, eval pipeline, block files) ─
# Functions that moved to tool_engine or dag_runner are re-exported here so
# existing callers (tests, eval harness) that import from executor continue to work.

from app.runtime.tool_engine import (  # noqa: F401, E402
    _resolve_refs,
    _resolve_remote_host,
    _dispatch_tool,
    _check_egress,
    _dry_run_mock,
    _INTEGRATION_HOSTS,
    _summarise_tool_call,
    _extract_git_evidence,
    _safe_subprocess_env,
    _tool_read_file,
    _tool_write_file,
    _tool_run_shell,
    _tool_search_code,
)

from app.runtime.dag_runner import (  # noqa: F401, E402
    _execute_dag,
    _execute_guard,
    _execute_memory_inner,
    _resolve_as_list,
    CredentialStore as _CredentialStore,  # already imported above from core.credentials
    _execute_brain,
    _execute_tool,
    _checkpoint_state,
    _load_checkpoint,
    _topological_sort,
    _find_skipped_blocks,
    _with_retry,
    _dispatch_single_block,
)
