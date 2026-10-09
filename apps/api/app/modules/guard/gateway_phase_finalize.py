"""Gateway lifecycle phase 7: v2 audit finalize (#2399).

Extracted verbatim from ``handle_gateway_request``. Runs deliberately
AFTER the response gate so a gate-blocked response never lands on top
of a pre-gate "ok" row. v1 gets its finalize inside
``transport.forward``'s ``_schedule_audit`` background path, so v1 is
not touched here.

Returns ``(response, v2_stream_wrapped)``. Nothing is mutated before a
raise, so the caller's except/finally see the same state as before.
"""
from __future__ import annotations

import time

from fastapi.responses import StreamingResponse

from app.modules.guard.gateway_attempt_outcome import served_model as _served_model
from app.modules.guard.gateway_request_state import GatewayCall
from app.modules.guard.gateway_v2_execute import _derive_v2_finalize_args
from app.modules.guard.gateway_v2_stream import (
    _wrap_v2_stream_finalize,
    _wrap_v2_stream_record_legacy,
)


async def finalize_v2(
    st: GatewayCall,
    _response,
    *,
    durable,
    _routing_meta: dict | None,
    _tool_stream_outcome,
    _v2_upstream_body_bytes: bytes | None,
):
    """Durable finalize (or legacy single-phase record when durable audit is off)."""
    from app.guard.audit import record as _record_audit
    from app.modules.guard.gateway_lifecycle import finalize_durable_row as _finalize_durable_row

    request, background, body = st.request, st.background, st.body
    workspace_id, clerk_user_id, ai_tool = st.workspace_id, st.clerk_user_id, st.ai_tool
    provider, model, started = st.provider, st.model, st.started
    _v2_plan, _durable_row_id = st.v2_plan, st.durable_row_id
    _audit_decision, _audit_rule_id = st.audit_decision, st.audit_rule_id
    _durable = durable
    _v2_stream_wrapped = False
    # Streaming: finalize can't run synchronously — we haven't seen the
    # vendor bytes yet. Wrap the stream generator so finalize fires when
    # the stream drains (or client disconnects). Non-streaming still
    # finalizes inline.
    # X4 — streaming lifetime. When v2 wraps a stream, the response
    # generator (owned by ASGI) is what actually reads the vendor's
    # bytes AFTER the handler returns. Cancelling the renewal task in the
    # handler's finally would kill lease renewal before the body is
    # consumed — the reconciler would flip the row to orphaned while it's
    # still live. Transfer renewal ownership to the stream wrapper: it
    # inherits ``_durable``, keeps renewal running while chunks flow, and
    # cancels it after finalize completes.
    if _v2_plan is not None and _durable_row_id:
        if isinstance(_response, StreamingResponse):
            _response = _wrap_v2_stream_finalize(
                _response,
                durable=_durable,
                row_id=_durable_row_id,
                workspace_id=workspace_id,
                provider=provider,
                model=_served_model(_routing_meta, model), model_alias=model,
                operation=request.url.path,  # P1-4: real op for normalizer family
                body=body,
                ingress_decision=_audit_decision,
                ingress_rule_id=_audit_rule_id,
                routing_meta=_routing_meta,
                clerk_user_id=clerk_user_id,
                ai_tool=ai_tool,
                user_email=st.user_email,
                started_monotonic=started,
                # R4 fix (reviewer P1): transfer reservation
                # ownership to the stream wrapper so settle
                # fires after the stream drains (not when the
                # handler returns and bytes still queued).
                reservations=st.reservations,
                _routing_meta=_routing_meta,
                # #2209 Session 6D — attribution.
                conductai_run_id=st.run_id,
                hook_session_id=st.hook_session_id,
                agent_identity_id=st.agent_identity_id,
                # Wall-clock deadline for the stream body. The
                # coordinator's ``wait_for`` only guarded header
                # arrival; the stream body has no timeout of its
                # own. Pull the profile's ``timeout_seconds`` as
                # the total-request budget.
                stream_deadline_seconds=(
                    _v2_plan.resolved.profile.timeout_seconds
                    if _v2_plan and _v2_plan.resolved else None
                ),
                tool_stream_outcome=_tool_stream_outcome,
                upstream_capture=_v2_plan.upstream_body,
            )
            _v2_stream_wrapped = True
        else:
            _v2_finalize = _derive_v2_finalize_args(
                post_gate_response=_response,
                pre_gate_upstream_body=_v2_upstream_body_bytes,
                ingress_decision=_audit_decision,
                ingress_rule_id=_audit_rule_id,
            )
            await _finalize_durable_row(
                row_id=_durable_row_id,
                workspace_id=workspace_id,
                decision=_v2_finalize["decision"],
                provider=provider,
                model=_served_model(_routing_meta, model),
                body=body,
                response_bytes=_v2_finalize["response_bytes"],
                duration_ms=int((time.monotonic() - started) * 1000),
                rule_id=_v2_finalize["rule_id"],
                routing_meta=_routing_meta,
                execution_status=_v2_finalize["execution_status"],
                result_summary=None,
                clerk_user_id=clerk_user_id,
                ai_tool=ai_tool,
                user_email=st.user_email,
            )
    elif _v2_plan is not None:
        # X2 — v2 executed but durable-audit was off (v2 flag +
        # durable-audit flag are independent). Without this branch
        # every v2 request skipped audit entirely: durable-audit's
        # ``_open_durable`` short-circuited to an empty row, the
        # v2 finalize block above required ``_durable_row_id`` and
        # was skipped, and v1's ``_record_audit`` never ran because
        # the v2 branch took the request. Fall back to the legacy
        # single-phase ``_record_audit`` so v2 traffic always lands
        # a row while durable-audit stays optional per workspace.
        if isinstance(_response, StreamingResponse):
            _response = _wrap_v2_stream_record_legacy(
                _response,
                background=background,
                workspace_id=workspace_id,
                clerk_user_id=clerk_user_id,
                ai_tool=ai_tool,
                provider=provider,
                model=_served_model(_routing_meta, model),
                body=body,
                prompt_summary=st.prompt_summary,
                user_email=st.user_email,
                conductai_run_id=st.run_id,
                conductai_workflow=st.workflow,
                conductai_workflow_id=st.workflow_id,
                hook_session_id=st.hook_session_id,
                routing_meta=_routing_meta,
                agent_identity_id=st.agent_identity_str,
                route=request.url.path,
                ingress_decision=_audit_decision,
                ingress_rule_id=_audit_rule_id,
                started_monotonic=started,
                record_audit_fn=_record_audit,
                tool_stream_outcome=_tool_stream_outcome,
                upstream_capture=_v2_plan.upstream_body,
                request_id=st.audit_request_id,
                # Z2 — deadline enforcement independent of audit
                # flag. Same profile timeout the durable-on
                # wrapper uses (Y3).
                stream_deadline_seconds=(
                    _v2_plan.resolved.profile.timeout_seconds
                    if _v2_plan and _v2_plan.resolved else None
                ),
            )
        else:
            _v2_finalize = _derive_v2_finalize_args(
                post_gate_response=_response,
                pre_gate_upstream_body=_v2_upstream_body_bytes,
                ingress_decision=_audit_decision,
                ingress_rule_id=_audit_rule_id,
            )
            background.add_task(
                _record_audit,
                workspace_id, clerk_user_id, ai_tool, provider, _served_model(_routing_meta, model),
                _v2_finalize["decision"],
                _v2_finalize["rule_id"],
                int((time.monotonic() - started) * 1000),
                body=body,
                response_bytes=_v2_finalize["response_bytes"],
                prompt_summary=st.prompt_summary,
                user_email=st.user_email,
                conductai_run_id=st.run_id,
                conductai_workflow=st.workflow,
                conductai_workflow_id=st.workflow_id,
                hook_session_id=st.hook_session_id,
                routing_meta=_routing_meta,
                execution_status=_v2_finalize["execution_status"],
                request_id=st.audit_request_id,
                agent_identity_id=st.agent_identity_str,
                route=request.url.path,
            )
    return _response, _v2_stream_wrapped
