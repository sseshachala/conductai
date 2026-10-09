"""Gateway lifecycle phase 3: prompt gate → rate limit (#2399).

Extracted verbatim from ``handle_gateway_request``: composed-engine
policy evaluation on the prompt (block / approval short-circuit), the
audit decision mapping, and the rate-limit check (v2 profile quotas or
the legacy workspace/agent limits). ``record_failure`` is the old
``_record_failure`` closure; it reads ``routing_meta`` at call time, as
the closure did.
"""
from __future__ import annotations

import time

import structlog
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.modules.guard.gateway_request_state import GatewayCall

log = structlog.get_logger(__name__)


async def evaluate_prompt_gate(st: GatewayCall) -> JSONResponse | None:
    """Step 4c — pre-call Guard policy evaluation (composed engine, #1225 Phase 4)."""
    from app.guard.audit import record as _record_audit
    from app.guard.policy import flatten_prompt as _flatten_prompt
    from app.guard.router import fail_closed as _fail_closed
    from app.runtime.accounting.estimator import estimate_tokens as _estimate_tokens

    request, background, body = st.request, st.background, st.body
    workspace_id, clerk_user_id = st.workspace_id, st.clerk_user_id
    provider, model, ai_tool = st.provider, st.model, st.ai_tool
    _agent_identity_id = st.agent_identity_id
    # P1 review fix — offloaded to threadpool with an owned session
    # (was sync DB-heavy eval on the event loop).
    prompt_summary = st.prompt_summary = _flatten_prompt(body)[:200]

    def _eval_prompt_policy_owned():
        from app.core.database import SessionLocal as _SL
        from app.core.workspace_context import set_workspace_rls
        from app.guard.policy import evaluate_composed as _eval_composed
        from app.guard.policy_types import PolicyContext as _PolicyContext
        _db_local = _SL()
        try:
            set_workspace_rls(_db_local, workspace_id)
            _ctx = _PolicyContext(
                workspace_id=workspace_id,
                clerk_user_id=clerk_user_id,
                agent_identity_id=str(_agent_identity_id) if _agent_identity_id else None,
                provider=provider,
                model=model,
                body=body,
                input_tokens=_estimate_tokens(body).input_tokens,
                db=_db_local,
                gate="prompt",
                risk_tier=st.agent_risk_tier,
                ai_tool=ai_tool or None,
                # #2159 PR 2 (#2156) — tool-name signals populated on
                # the request-gate side. Empty list stays semantically
                # distinct from None (unset) so rules can distinguish.
                tool_names_offered=st.tools_offered or None,
                tool_names_supplied=st.tool_names_supplied or None,
            )
            return _eval_composed(_ctx)
        finally:
            _db_local.close()

    _pd = await run_in_threadpool(_eval_prompt_policy_owned)
    decision = st.decision = _pd.extras.get("raw") or {
        "action": _pd.action.value,
        "rule_id": _pd.rule_id,
        "message": _pd.reason,
        "matched_rules": _pd.matched_rules,
        "defense_score": _pd.defense_score,
        "inject_guidance": _pd.inject_guidance,
        "guidance": _pd.guidance,
        "rule": _pd.extras.get("rule"),
    }
    _action = _pd.action.value
    st.guidance_text = _pd.guidance if _pd.inject_guidance else None

    if _pd.blocks:
        from app.modules.guard.routers._proxy_helpers import render_block as _render_block
        return _render_block(
            _pd, background, workspace_id, clerk_user_id, ai_tool, provider,
            model, body, prompt_summary, st.user_email, st.run_id, st.workflow,
            st.workflow_id, st.hook_session_id, st.started, _record_audit, _fail_closed,
            is_trial=st.is_trial,
            routing_meta=st.routing_meta, agent_identity_id=_agent_identity_id,
            route=request.url.path,
        )

    if _pd.needs_approval:
        from app.modules.guard.routers._proxy_helpers import render_approval as _render_approval
        return _render_approval(
            _pd, background, workspace_id, clerk_user_id, ai_tool, provider,
            model, body, prompt_summary, st.user_email, st.run_id, st.workflow,
            st.workflow_id, st.hook_session_id, st.started, _record_audit,
            routing_meta=st.routing_meta, agent_identity_id=_agent_identity_id,
            route=request.url.path,
        )

    # Map internal action to audit decision string
    st.audit_decision = "warned" if _action == "WARN" else "allowed"
    st.audit_rule_id = decision["rule_id"] if _action == "WARN" else None
    return None


def record_failure(st: GatewayCall, status: int, message: str, *, rule_id: str | None = None) -> None:
    """Queue the single-phase audit row for a pre-dispatch refusal."""
    from app.guard.audit import record as _record_audit

    st.background.add_task(
        _record_audit,
        st.workspace_id, st.clerk_user_id, st.ai_tool, st.provider, st.model,
        "blocked" if status in (403, 429) else st.audit_decision,
        rule_id or st.audit_rule_id,
        int((time.monotonic() - st.started) * 1000),
        body=st.body, response_bytes=None, prompt_summary=st.prompt_summary,
        user_email=st.user_email, conductai_run_id=st.run_id,
        conductai_workflow=st.workflow, conductai_workflow_id=st.workflow_id,
        hook_session_id=st.hook_session_id, routing_meta=st.routing_meta,
        execution_status="error", result_summary=f"HTTP {status}: {message}"[:500],
        agent_identity_id=st.agent_identity_str,
        route=st.request.url.path,
    )


async def check_rate_limits(st: GatewayCall) -> JSONResponse | None:
    """v2 checks shared profile and agent-wide quotas atomically.
    Legacy traffic keeps its original workspace/agent limits."""
    from app.guard.router import fail_closed as _fail_closed
    from app.modules.guard.rate_limit import check_rate_limit as _check_rate_limit
    from app.runtime.accounting.estimator import estimate_tokens as _estimate_tokens

    workspace_id, body, _v2_plan = st.workspace_id, st.body, st.v2_plan
    _agent_identity_id = st.agent_identity_id

    def _rate_check_owned():
        from app.core.database import SessionLocal as _SL
        from app.core.workspace_context import set_workspace_rls
        _db_local = _SL()
        try:
            if _v2_plan is not None:
                from app.modules.guard.gateway_profile_rate_limit import check_profile_rate_limit, reserved_profile_tokens
                return check_profile_rate_limit(
                    _db_local, workspace_id=workspace_id,
                    profile_id=getattr(_v2_plan.resolved, "profile_id", None),
                    revision_id=_v2_plan.resolved.revision_id,
                    agent_identity_id=str(_agent_identity_id) if _agent_identity_id else None,
                    reserved_tokens=reserved_profile_tokens(body, _v2_plan.operation),
                )
            set_workspace_rls(_db_local, workspace_id)
            return _check_rate_limit(
                _db_local,
                workspace_id=workspace_id,
                agent_identity_id=str(_agent_identity_id) if _agent_identity_id else None,
                input_tokens=_estimate_tokens(body).input_tokens,
                fail_closed=st.canonical_profile and settings.environment == "production",
            )
        finally:
            _db_local.close()
    _rate = await run_in_threadpool(_rate_check_owned)
    st.profile_rate_admission = getattr(_rate, "admission", None)
    if _rate.limited:
        log.info(
            "guard.proxy.rate_limited",
            workspace_id=workspace_id,
            scope=_rate.scope,
            metric=_rate.metric,
            limit=_rate.limit,
            current=_rate.current,
        )
        status = getattr(_rate, "status", 429)
        record_failure(st, status, _rate.reason, rule_id="rate-limit")
        response = _fail_closed(status, _rate.reason)
        response.headers["Retry-After"] = str(getattr(_rate, "retry_after", 60))
        return response
    return None
