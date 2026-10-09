"""Gateway lifecycle phase 6: dispatch → response gates (#2399).

Extracted verbatim from ``handle_gateway_request``. The handler keeps the
dispatch boundary itself (``_dispatched = True`` immediately before the
upstream await) and the try/except/finally that owns durable close and
settlement; this module holds the pieces it calls:

- ``v2_dispatch_inputs`` / ``v2_upstream_snapshot`` around ``_execute_v2``
- ``forward_v1``: the legacy ``transport.forward`` call + audit_args tuple
- ``apply_tool_call_gate`` / ``wrap_stream_tool_gate`` / ``apply_response_gate``

Every gate returns its new values instead of mutating shared state, and
each return is assigned in one statement, so a raise leaves the
handler's locals exactly as the inline code did.
"""
from __future__ import annotations

import structlog
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.modules.guard.gateway_request_state import GatewayCall
from app.modules.guard.gateway_v2_execute import _build_stream_tool_policy_check
from app.modules.guard.gateway_v2_plan import _build_policy_check, _v2_allowlisted_headers

log = structlog.get_logger(__name__)


def apply_tool_call_gate(
    response: JSONResponse,
    routing_meta: dict | None,
    *,
    workspace_id: str,
    provider: str,
    model: str,
) -> tuple[JSONResponse, dict | None]:
    """#2159 PR 2 — tool-call scanner + reason marker.

    Contract:
      - Parses ``response.body`` as JSON.
      - Walks ``choices[].message.tool_calls[].function.arguments``,
        redacting string leaves via ``tools_validator.scan_response_tool_calls``.
      - On ``RedactionFailure``: returns (502 envelope, routing_meta with
        ``response_gate_reason=validation_failure`` and empty
        ``tool_calls_generated``). Upstream cost stays on the audit row
        because inference already happened; only the tool_call is refused.
      - Otherwise: returns (response with redacted body substituted,
        routing_meta with ``tool_calls_generated`` populated).

    Never raises. The existing composed-engine ``_apply_response_gate``
    runs AFTER this helper — a 502 here short-circuits the gate; a
    successful scan hands off the sanitised body to the gate for
    policy evaluation. The gate's own 451 result is marked separately
    in the caller so the two ``response_gate_reason`` values stay
    distinct.
    """
    import json as _json_tc
    from app.modules.guard.tools_validator import (
        ResponseGateReason,
        scan_response_tool_calls,
    )

    try:
        _resp_parsed = _json_tc.loads(response.body or b"{}")
    except Exception:
        _resp_parsed = {}
    scan = scan_response_tool_calls(_resp_parsed)
    if scan.error is not None:
        log.warning(
            "guard.response.tool_args_validation_failed",
            workspace_id=workspace_id, provider=provider, model=model,
            source=scan.error.source, reason=scan.error.reason,
        )
        routing_meta = {
            **(routing_meta or {}),
            "response_gate_reason": ResponseGateReason.VALIDATION_FAILURE,
            "tool_calls_generated": [],
        }
        response = JSONResponse(
            status_code=502,
            content={
                "error": {
                    "type": "conduct_gateway_tool_arguments_validation_failed",
                    "message": (
                        "Tool_call arguments failed validation and cannot "
                        "be safely delivered. Upstream inference completed "
                        "and is billed; the tool call is refused."
                    ),
                    "detail": scan.error.reason,
                    "source": scan.error.source,
                    "gate": "response",
                }
            },
        )
        return response, routing_meta

    correlation_ids: dict[str, str] = {}
    if scan.generated_calls:
        # #2158 — assign a correlation id per generated tool_call.
        # Runtime executor reads the X-Conduct-Tool-Correlation-Ids
        # response header and attaches it to its own Flight Recorder
        # entry so both sides can be joined. Stored alongside
        # tool_calls_generated in routing_meta for audit-side lookup.
        from app.modules.guard.tools_validator import (
            generate_tool_call_correlation_ids as _gen_corr,
        )
        correlation_ids = _gen_corr(scan.generated_calls)
        routing_meta = {
            **(routing_meta or {}),
            "tool_calls_generated": scan.generated_calls,
            "tool_call_correlation_ids": correlation_ids,
        }

    if scan.scanned_body is not None and scan.scanned_body is not _resp_parsed:
        response = JSONResponse(
            status_code=response.status_code,
            content=scan.scanned_body,
        )

    if correlation_ids:
        # Attach correlation header on the outgoing response. Existing
        # headers preserved by JSONResponse are all defaults (content
        # type + length), so setting one custom header is safe.
        from app.modules.guard.tools_validator import (
            encode_correlation_header as _enc_corr,
        )
        response.headers["X-Conduct-Tool-Correlation-Ids"] = _enc_corr(correlation_ids)

    return response, routing_meta


def v2_dispatch_inputs(st: GatewayCall):
    """X1 per-target policy re-eval closure + X7 vendor header allowlist.

    The ingress policy eval runs against the cond-* alias; the transport
    substitutes ``target.model`` before wire, so rules keyed on the real
    target model need a per-target check. block → skip target (records a
    PolicyBlock attempt); all blocked → AllAttemptsFailed → 451.
    """
    from app.modules.auth.federation.gateway import delegated_policy_check

    _policy_check = _build_policy_check(
        workspace_id=st.workspace_id,
        clerk_user_id=st.clerk_user_id,
        agent_identity_id=st.agent_identity_str,
        fallback_provider=st.provider,
        body=st.body,
        risk_tier=st.agent_risk_tier,
        ai_tool=st.ai_tool,
    )
    # X7 — vendor-specific client headers (``anthropic-beta``,
    # ``openai-organization``, ...) reach v2 targets via a
    # v2-side allowlist (stricter than v1's blanket forward).
    _v2_client_headers = _v2_allowlisted_headers(st.extra_headers)
    _policy_check = delegated_policy_check(_policy_check, st.federation)
    return _policy_check, _v2_client_headers


def v2_upstream_snapshot(response, plan) -> bytes | None:
    """Snapshot the upstream body BEFORE the response gate runs.

    If the gate blocks, the response is replaced with a 451 envelope
    carrying no token usage; finalize + settle need the upstream bytes so
    cost and token accounting still work. Streaming bodies are not
    materialised yet — the stream wrapper collects them as they pass.
    """
    if isinstance(response, StreamingResponse):
        return None
    try:
        return bytes(plan.upstream_body) or None
    except Exception:
        return None


async def forward_v1(st: GatewayCall):
    """Legacy ``transport.forward``; its ``_schedule_audit`` finalizes the row."""
    from app.guard.router import upstream as _forward

    request = st.request
    return await st.transport.forward(
        sender=_forward,
        upstream=st.upstream,
        path=st.upstream_path,
        body=st.body,
        real_key=st.real_key,
        auth_header_out=st.auth_header_out,
        bearer=st.bearer,
        is_stream=st.is_stream,
        extra_headers=st.extra_headers,
        background=st.background,
        audit_args=(
            st.workspace_id,
            st.clerk_user_id,
            st.ai_tool,
            st.provider,
            st.model,
            st.audit_decision,
            st.audit_rule_id,
            st.started,
            st.body,
            st.prompt_summary,
            st.user_email,
            st.run_id,
            st.workflow,
            st.workflow_id,
            st.hook_session_id,
            st.routing_meta,
            # Phase 0 of #1959 — index 16 = resolved agent identity id. Read by
            # router._schedule_audit and forwarded to audit.record so Gateway
            # rows carry agent attribution end-to-end.
            st.agent_identity_str,
            # Follow-up to #1971 — index 17 = FastAPI request path so
            # /proxy/* vs /gateway/v1/* is queryable from audit rows.
            request.url.path,
            # Phase 2 of #1959 — index 18 = durable row id. When set,
            # _schedule_audit dispatches to finalize() instead of record().
            st.durable_row_id,
            st.audit_request_id,
        ),
        upstream_api_key=st.upstream_key,
        vendor_key=st.vault_key_val,
        provider=st.provider,
    )


def wrap_stream_tool_gate(st: GatewayCall, _response, _routing_meta):
    """#2155 — streaming tool_call gate. Returns ``(response, outcome)``.

    Same invariant as non-streaming (no raw unsafe tool_call arguments
    reach the client) but buffered across SSE deltas: tool_call arg
    fragments are held until ``finish_reason: "tool_calls"``, run through
    the same validator + redactor as ``apply_tool_call_gate``, and
    re-emitted as one synthetic frame. Text deltas stream unchanged. Runs
    BEFORE the buffered-text response gate so that gate scans what the
    client will actually see. No-op when the body has no ``tools`` or the
    flag is off — the shim's 400 rejection is the fallback.
    """
    _v2_plan = st.v2_plan
    if not (
        st.operation == "inference"
        and st.is_stream
        and isinstance(_response, StreamingResponse)
        and _response.status_code < 400
        and st.body.get("tools")
        and (settings.guard_gateway_tools_stream_enabled or _v2_plan is not None)
    ):
        return _response, None
    from app.modules.guard.tools_stream_gate import (
        wrap_tool_stream as _wrap_tool_stream_gate,
        StreamGateOutcome as _StreamGateOutcome,
    )
    # #2173 P1 — shared outcome + composed-engine policy check. Outcome
    # mutates as the stream drains; _wrap_v2_stream_finalize reads it to
    # set decision + execution_status and to merge correlation_ids into
    # routing_meta instead of a false-positive "allowed / ok".
    _tool_stream_outcome = _StreamGateOutcome()
    _stream_operation = (
        "openai_chat_completions" if _v2_plan and _v2_plan.needs_anthropic_conversion
        else _v2_plan.operation if _v2_plan
        else "openai_responses" if st.request.url.path.endswith("/responses")
        else "anthropic_messages" if st.provider == "anthropic"
        else "openai_chat_completions"
    )
    _stream_gate = _wrap_tool_stream_gate
    _stream_gate_args = {}
    if _stream_operation != "openai_chat_completions":
        from app.modules.guard.tools_native_stream_gate import wrap_native_tool_stream
        _stream_gate = wrap_native_tool_stream
        _stream_gate_args = {"operation": _stream_operation}
    _stream_policy_check = _build_stream_tool_policy_check(
        workspace_id=st.workspace_id,
        clerk_user_id=st.clerk_user_id,
        agent_identity_id=st.agent_identity_str,
        agent_risk_tier=st.agent_risk_tier,
        ai_tool=st.ai_tool,
        provider=st.provider,
        model=st.model,
        body=st.body,
        routing_meta=_routing_meta,
    )
    _response = StreamingResponse(
        _stream_gate(
            _response.body_iterator,
            outcome=_tool_stream_outcome,
            policy_check=_stream_policy_check,
            **_stream_gate_args,
        ),
        media_type=_response.media_type,
        headers=dict(_response.headers),
        status_code=_response.status_code,
    )
    return _response, _tool_stream_outcome


async def apply_response_gate(st: GatewayCall, _response, _routing_meta):
    """#1733 PR 4/5 — response gate. Returns ``(response, routing_meta)``.

    Non-streaming: composed-engine gate (only when the tool-call scanner
    didn't already 502). Streaming: buffered end-of-stream scan wrapper.
    """
    from app.modules.guard.gateway_helpers import _apply_response_gate, _wrap_streaming_response

    workspace_id, provider, model = st.workspace_id, st.provider, st.model
    if (
        st.operation == "inference"
        and not st.is_stream
        and isinstance(_response, JSONResponse)
        and _response.status_code < 400
    ):
        # PR 2 Commit 3 — response gate policy eval hits DB; offload.
        import functools as _ft
        # #2159 PR 2 (#2156) — thread tool-name signals from
        # routing_meta into the response-gate PolicyContext so
        # composed-engine rules can select on tool identity.
        _rm_now = _routing_meta or {}
        _tng_names = [
            tc.get("name", "") for tc in (_rm_now.get("tool_calls_generated") or [])
            if isinstance(tc, dict) and tc.get("name")
        ] or None
        _response = await run_in_threadpool(
            _ft.partial(
                _apply_response_gate,
                _response,
                workspace_id=workspace_id,
                provider=provider,
                model=model,
                clerk_user_id=st.clerk_user_id,
                agent_identity_id=st.agent_identity_id,
                agent_risk_tier=st.agent_risk_tier,
                ai_tool=st.ai_tool,
                tool_names_offered=_rm_now.get("tools_offered") or None,
                tool_names_generated=_tng_names,
                tool_names_supplied=_rm_now.get("tool_names_supplied") or None,
            )
        )
        # #2159 PR 2 — mark policy-block reason on audit when the
        # existing composed-engine gate 451'd. The scanner's
        # ``VALIDATION_FAILURE`` reason is distinct from this one so ops
        # can tell the two apart.
        if _response.status_code == 451:
            from app.modules.guard.tools_validator import (
                ResponseGateReason as _RGR_block,
            )
            _routing_meta = {
                **(_routing_meta or {}),
                "response_gate_reason": _RGR_block.POLICY_BLOCK,
            }
    # #1733 PR 5: response gate (streaming, buffered end-of-stream scan).
    elif (
        st.operation == "inference"
        and st.is_stream
        and isinstance(_response, StreamingResponse)
        and _response.status_code < 400
    ):
        _response = _wrap_streaming_response(
            _response, workspace_id=workspace_id, provider=provider, model=model,
            clerk_user_id=st.clerk_user_id, agent_identity_id=st.agent_identity_id,
            agent_risk_tier=st.agent_risk_tier,
            ai_tool=st.ai_tool,
        )
    return _response, _routing_meta
