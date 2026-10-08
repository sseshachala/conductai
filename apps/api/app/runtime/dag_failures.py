"""DAG runner failure classification and Lens block tee (split from dag_runner.py; re-exported there)."""
from __future__ import annotations

import re
from typing import Any

import structlog

from app.runtime.exceptions import ClarificationRequired
from app.runtime.llm_client import GuardProxyBlocked, LLMUpstreamError

log = structlog.get_logger("app.runtime.dag_runner")


def _tee_block(run, block_id: str, event_type: str, extra: dict | None = None) -> None:
    """Tee a block-level event to the Lens session stream (#1480 PR 7).

    No-op when run.session_id is None (non-Lens runs). Fail-open so a
    Redis outage or import glitch never breaks the worker.
    """
    try:
        from app.modules.glens.run_events import publish_run_block_event
        publish_run_block_event(run, block_id, event_type, extra)
    except Exception:
        pass


def _classify_failure(
    exc: Exception,
    block_id: str | None = None,
    state: dict | None = None,
) -> dict[str, Any]:
    """Normalize runtime failures into a structured, user-actionable summary.

    `state` is optional so existing call sites keep working. When provided, we
    read state["__governance"] to enrich Guard-block hints with the matched
    snippet + non_overridable-aware next_action text.
    """
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
    elif isinstance(exc, GuardProxyBlocked) and exc.error_type == "conduct_guard_proxy":
        # Proxy configuration error (BYO LLM key missing, upstream misconfig,
        # etc.). Not a workflow bug — an operator needs to fix the workspace
        # proxy settings. Distinct from guard_block, which flows through the
        # existing Guard string-match branch above.
        code = "PROXY_CONFIG_ERROR"
        category = "configuration"
        stop_reason = "proxy_misconfigured"
        next_action = (
            "Conduct proxy returned a configuration error: "
            + (exc.message if hasattr(exc, "message") else str(exc))
            + ". Check Settings → Modules → Guard proxy config and BYO LLM keys."
        )
    elif isinstance(exc, LLMUpstreamError):
        # CF/Render/WAF intercepted the LLM proxy request. Not our app's fault.
        # The exception message is already short and safe (no HTML); the full
        # diagnostic (cf_ray, render_request_id, body_snippet) is in the
        # llm_upstream_blocked event emitted by brain_block.
        code = "LLM_UPSTREAM_BLOCKED"
        category = "infrastructure"
        stop_reason = "upstream_blocked"
        cf_ray = getattr(exc, "cf_ray", None)
        request_id = getattr(exc, "request_id", None)
        next_action = (
            "LLM proxy request was blocked by an upstream layer (CF WAF, Render edge). "
            + (f"Cloudflare ray: {cf_ray}. " if cf_ray else "")
            + (f"Render request: {request_id}. " if request_id else "")
            + "Retry the run; if it fails repeatedly, check /run-events for llm_upstream_blocked entries "
            + "and share the ray ID with support."
        )
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
        # State carries governance metadata from guard_block — includes
        # non_overridable flag and the matched snippet so we can shape a
        # useful next_action instead of the generic "disable Guard" hint.
        _gov = {}
        if isinstance(state, dict):
            _gov = state.get("__governance") or {}
        _non_overridable = bool(_gov.get("non_overridable"))
        _snippet = (_gov.get("matched_snippet") or "").strip()
        if _non_overridable:
            _hint = (
                "This rule cannot be disabled (compliance-critical). "
                "Adjust the agent's tool call to comply, or contact your Guard admin "
                "for an exception request."
            )
        else:
            _hint = (
                "Disable Guard for this workflow in Settings → ConductGuard, "
                "or change the rule action at /guard/policies."
            )
        next_action = (
            (f"Guard rule '{rule_id}' blocked this step. " if rule_id else "Guard blocked this step. ")
            + (f"Matched near: '…{_snippet}…'. " if _snippet else "")
            + _hint
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

    # Include the traceback tail so operators can pinpoint the failure without
    # hunting through Render logs. Trimmed to last 20 lines — enough to spot
    # the exact file:line, small enough not to blow up the event payload.
    import traceback as _tb
    _tb_lines = _tb.format_exception(type(exc), exc, exc.__traceback__)
    _tb_tail = "".join(_tb_lines)[-2000:]

    return {
        "code": code,
        "category": category,
        "stop_reason": stop_reason,
        "message": msg,
        "block_id": block_id,
        "next_action": next_action,
        "traceback": _tb_tail,
    }

