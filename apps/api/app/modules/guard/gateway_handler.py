"""Canonical Gateway request entry point.

Owns the full Gateway request lifecycle: authenticate the caller (member
token, agent identity, or run token), evaluate Guard policies, open a
durable-audit row via ``gateway_lifecycle``, forward to the vendor, apply
the response gate, and close the audit row. Legacy ``/proxy/*`` route
decorators in ``routers/proxy.py`` delegate here — no new Gateway behavior
is allowed to grow on that legacy surface.

#2399 — ``handle_gateway_request`` orchestrates named lifecycle phases,
in the same order and with the same await points as the old single
function:

1. ``gateway_phase_ingress``   identity → admission acquire
2. ``gateway_phase_routing``   body → model routing → v2 plan → context
3. ``gateway_phase_policy``    prompt gate → rate limit
4. ``gateway_phase_upstream``  v1 credentials → outbound body/headers
5. ``gateway_phase_reserve``   durable acceptance → budget reservation
6. ``gateway_phase_dispatch``  execute attempt(s) → response gates
7. ``gateway_phase_finalize``  v2 audit finalize
8. ``gateway_phase_settle``    receipts → settlement (non-streaming)

The dispatch boundary, the exception-path audit, durable close, and the
admission / profile-rate cleanup stay here so their ordering is visible
in one place. Per-request state lives on ``GatewayCall``.
"""
from __future__ import annotations

import time

from starlette.concurrency import run_in_threadpool

import structlog
from fastapi import BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
from app.modules.auth.federation.resolver import FederationDenied
from app.modules.guard.gateway_phase_dispatch import apply_tool_call_gate  # noqa: F401 — re-export
from app.modules.guard.gateway_request_state import GatewayCall
from app.modules.guard.gateway_v2_plan import (  # noqa: F401 — re-exports
    _V2_HEADER_ALLOWLIST,
    _V2Plan,
    _build_policy_check,
    _build_v2_plan,
    _build_v2_plan_owned,
    _extract_cond_code,
    _v2_allowlisted_headers,
)
from app.modules.guard.gateway_v2_execute import (  # noqa: F401 — re-exports
    _STREAM_HOP_HEADERS,
    _build_stream_tool_policy_check,
    _build_v2_stream_response,
    _derive_v2_finalize_args,
    _execute_v2,
    _merge_routing_meta,
)
from app.modules.guard.gateway_v2_stream import (  # noqa: F401 — re-exports
    _close_stream_iterator,
    _wrap_stream_receipts,
    _wrap_v2_stream_finalize,
    _wrap_v2_stream_record_legacy,
)


log = structlog.get_logger(__name__)


async def handle_gateway_request(
    request: Request,
    background: BackgroundTasks,
    *,
    provider: str,
    upstream_path: str,
    auth_header_in: str,
    auth_header_out: str,
    auth_header_fallback: str | None = None,
    bearer: bool = False,
    canonical_profile: bool = False,
    operation: str = "inference",
) -> StreamingResponse | JSONResponse:
    """One implementation, three providers — only the URL + auth header shape differs."""
    from app.guard.audit import record as _record_audit
    from app.modules.guard import (
        gateway_phase_dispatch as _dispatch,
        gateway_phase_finalize as _finalize,
        gateway_phase_ingress as _ingress,
        gateway_phase_policy as _policy,
        gateway_phase_reserve as _reserve,
        gateway_phase_routing as _routing,
        gateway_phase_settle as _settle,
        gateway_phase_upstream as _upstream,
    )
    from app.modules.guard.gateway_attempt_outcome import merge_attempts as _merge_attempts  # #2403
    from app.modules.guard.gateway_attempt_outcome import served_model as _served_model, wrap_stream_finally

    started = time.monotonic()
    st = GatewayCall(
        request=request, background=background, provider=provider,
        upstream_path=upstream_path, auth_header_in=auth_header_in,
        auth_header_out=auth_header_out, auth_header_fallback=auth_header_fallback,
        bearer=bearer, canonical_profile=canonical_profile, operation=operation,
        started=started,
    )

    # 1. Member token / internal key — 401 before any admission state.
    _early = _ingress.extract_token(st)
    if _early is not None:
        return _early

    # PR 2 (#2056) admission state — kill switch: ADMISSION_ENABLED. The
    # ticket, profile-rate admission and v2 plan live on ``st`` so the
    # outer finally sees them on every exit path.
    _admission_streamed = False
    _profile_rate_streamed = False

    try:
        # 2–5. Each phase returns a response to short-circuit, else None.
        if (_early := await _ingress.resolve_caller(st, operation=operation)) is not None:
            return _early
        _early = await _routing.parse_and_route(st, build_v2_plan_owned=_build_v2_plan_owned)
        if _early is not None:
            return _early
        await _routing.load_request_context(st)
        if (_early := await _policy.evaluate_prompt_gate(st)) is not None:
            return _early
        if (_early := await _policy.check_rate_limits(st)) is not None:
            return _early
        if (_early := await _upstream.resolve_upstream_credentials(st)) is not None:
            return _early
        _upstream.prepare_outbound_request(st)
        if (_early := await _reserve.open_audit_and_reserve(st)) is not None:
            return _early

        from app.modules.auth.federation.gateway import recheck_gateway
        from app.modules.guard.gateway_lifecycle import close_durable_row as _close_durable
        from app.modules.guard.gateway_lifecycle import finalize_durable_row as _finalize_durable_row

        workspace_id, clerk_user_id, ai_tool, model = st.workspace_id, st.clerk_user_id, st.ai_tool, st.model
        body, prompt_summary, _user_email = st.body, st.prompt_summary, st.user_email
        _run_id, _workflow, _workflow_id = st.run_id, st.workflow, st.workflow_id
        _hook_session_id, _agent_identity_id = st.hook_session_id, st.agent_identity_id
        _v2_plan, _durable, _durable_row_id = st.v2_plan, st.durable, st.durable_row_id
        _audit_request_id, _routing_meta = st.audit_request_id, st.routing_meta

        # P1: forward + response-gate run under an exception-safe
        # lifecycle. Guarantees:
        #   - close_durable_row runs on every exit path (finally), so the
        #     whole-request heartbeat never renews an abandoned row.
        #   - On exception, best-effort finalize with 'error' / 'interrupted'
        #     so the row lands terminated immediately instead of waiting on
        #     the reconciler's lease-expiry sweep.
        import asyncio as _asyncio
        # X4 — set before the try/finally so ``finally: _close_durable``
        # can read it even if an early raise skips the wrap.
        _v2_stream_wrapped = False
        _tool_stream_outcome = None  # set by the streaming tool-gate wrap
        _dispatched = False  # flipped to True right before any upstream call
        # The finally references ``_response`` when computing actuals for
        # settle. Any raise inside the try (v2 502 from _execute_v2, v1
        # forwarder error, etc.) leaves the assignment unbound and Python
        # raises UnboundLocalError from the finally, masking the real
        # HTTPException as a generic 500. Initialise here so the
        # finally can guard via ``if _response is not None``.
        _response = None
        _v2_upstream_body_bytes = None
        try:
            if _v2_plan is not None:
                # #2004 Phase 1 — v2 executes the coordinator + LiteLLM SDK
                # transport inside the same lifecycle as v1: same audit row,
                # same response gate, same finalize path. Finalize is
                # deferred to AFTER the response gate. PR 2.5 — ``stream``
                # lets the coordinator return a live StreamingResponse.
                _policy_check, _v2_client_headers = _dispatch.v2_dispatch_inputs(st)
                # ── PR-A2b: dispatch boundary ──
                # Flip BEFORE bytes fly. Any exception past this point
                # is treated as "may have dispatched" -> settle marks
                # PENDING_RECONCILER (never releases, reconciler owns
                # cleanup). Releasing after real spend would silently
                # drop billed cost.
                _dispatched = True
                _response = await _execute_v2(
                    plan=_v2_plan, body=body, stream=st.is_stream,
                    policy_check=_policy_check,
                    client_headers=_v2_client_headers,
                )
                # Reflect coordinator attempt records back into routing_meta
                # so the durable audit row lands with the full attempt list.
                _routing_meta = _merge_routing_meta(_routing_meta, _v2_plan.last_meta)
                _v2_upstream_body_bytes = _dispatch.v2_upstream_snapshot(_response, _v2_plan)
            else:
                # ── PR-A2b: dispatch boundary (legacy path) ──
                await run_in_threadpool(recheck_gateway, st.federation)
                _dispatched = True
                _response = await _dispatch.forward_v1(st)
            # #2159 PR 2 — scan tool_call arguments BEFORE the composed-
            # engine gate (RedactionFailure → 502 terminal, redacted body
            # substituted otherwise, routing_meta updated).
            if (
                operation == "inference"
                and not st.is_stream
                and isinstance(_response, JSONResponse)
                and _response.status_code < 400
            ):
                _response, _routing_meta = apply_tool_call_gate(
                    _response, _routing_meta,
                    workspace_id=workspace_id, provider=provider, model=model,
                )
            # #2155 — streaming tool_call gate, then the #1733 response gate.
            _response, _tool_stream_outcome = _dispatch.wrap_stream_tool_gate(st, _response, _routing_meta)
            _response, _routing_meta = await _dispatch.apply_response_gate(st, _response, _routing_meta)
            # v2 finalize — deliberately AFTER the response gate. A wrapped
            # v2 stream takes over renewal ownership (``_v2_stream_wrapped``).
            _response, _v2_stream_wrapped = await _finalize.finalize_v2(
                st, _response,
                durable=_durable,
                _routing_meta=_routing_meta,
                _tool_stream_outcome=_tool_stream_outcome,
                _v2_upstream_body_bytes=_v2_upstream_body_bytes,
            )
        except BaseException as _forward_exc:  # noqa: BLE001 — need CancelledError too
            _routing_meta = _merge_attempts(_routing_meta, _v2_plan)  # #2403 item 4: all-failed attempts
            # Best-effort finalize so the row lands terminated immediately
            # instead of waiting on the reconciler's lease sweep. WHERE
            # lifecycle_state = 'accepted' in audit.finalize means this is
            # a no-op if the transport / _stream_chunks already finalized
            # (e.g. an error partway through streaming).
            _is_cancel = isinstance(_forward_exc, _asyncio.CancelledError)
            _exec_status = "interrupted" if _is_cancel else "error"
            _result_summary = (
                "Request cancelled during upstream forward"
                if _is_cancel
                else f"forward/gate exception: {type(_forward_exc).__name__}: {str(_forward_exc)[:400]}"
            )
            if _durable_row_id:
                try:
                    await _finalize_durable_row(
                        row_id=_durable_row_id,
                        workspace_id=workspace_id,
                        decision="error",
                        provider=provider,
                        model=_served_model(_routing_meta, model),
                        body=body,
                        response_bytes=None,
                        duration_ms=int((time.monotonic() - started) * 1000),
                        rule_id=None,
                        routing_meta=_routing_meta,
                        execution_status=_exec_status,
                        result_summary=_result_summary,
                        clerk_user_id=clerk_user_id,
                        ai_tool=ai_tool,
                        user_email=_user_email,
                    )
                except Exception:
                    log.exception("guard.gateway.error_finalize_failed", row_id=_durable_row_id)
            elif _v2_plan is not None:
                # Z1 fix — v2 executed with durable-audit OFF and the
                # request raised. Y2 originally used
                # ``background.add_task(_record_audit, ...)``, but FastAPI
                # only runs queued background tasks AFTER the response is
                # returned normally — a raise here propagates to FastAPI's
                # error handler, which returns a 5xx without draining the
                # queued task. Net effect: exception-path v2 requests with
                # durable-audit off wrote ZERO rows.
                #
                # Fix: run ``_record_audit`` synchronously in a thread
                # (``asyncio.to_thread``) BEFORE re-raising. Failure of the
                # writer itself is logged, never re-raised, so the original
                # exception the caller sees is preserved.
                try:
                    await _asyncio.to_thread(
                        _record_audit,
                        workspace_id, clerk_user_id, ai_tool, provider, _served_model(_routing_meta, model),
                        "error",
                        None,   # rule_id
                        int((time.monotonic() - started) * 1000),
                        body=body,
                        response_bytes=None,
                        prompt_summary=prompt_summary,
                        user_email=_user_email,
                        conductai_run_id=_run_id,
                        conductai_workflow=_workflow,
                        conductai_workflow_id=_workflow_id,
                        hook_session_id=_hook_session_id,
                        routing_meta=_routing_meta,
                        execution_status=_exec_status,
                        result_summary=_result_summary,
                        request_id=_audit_request_id,
                        agent_identity_id=(
                            str(_agent_identity_id) if _agent_identity_id else None
                        ),
                        route=request.url.path,
                    )
                except Exception:
                    log.exception("guard.gateway.v2.error_record_audit_failed")
            raise
        finally:
            # X4 — v2 streaming transfers renewal ownership to
            # ``_wrap_v2_stream_finalize``; its ``finally`` calls
            # ``_close_durable`` after the stream drains. Every other exit
            # path (non-streaming, error, cancel before we ever wrapped)
            # cancels here — idempotent.
            if not _v2_stream_wrapped:
                await _close_durable(_durable)
            # Live-write settlement (receipts first, then reservations).
            await _settle.settle_request(
                st,
                _dispatched=_dispatched,
                _response=_response,
                _v2_upstream_body_bytes=_v2_upstream_body_bytes,
                _routing_meta=_routing_meta,
            )

        if isinstance(_response, StreamingResponse) and (_v2_plan is None or not _durable_row_id):
            _response = _wrap_stream_receipts(
                _response, upstream_capture=(_v2_plan.upstream_body if _v2_plan else None),
                workspace_id=workspace_id, request_id=_audit_request_id,
                provider=provider, model=_served_model(_routing_meta, model), model_alias=(model if _v2_plan else None), operation=request.url.path,
                developer_external_id=clerk_user_id, agent_identity_id=_agent_identity_id,
                source="gateway", client_tool=ai_tool, attempts_meta=(_routing_meta or {}).get("attempts"),
                workflow_run_id=_run_id, hook_session_id=_hook_session_id,
            )

        if st.profile_rate_admission is not None and isinstance(_response, StreamingResponse):
            from app.modules.guard.gateway_profile_rate_limit import wrap_profile_rate_stream
            _response = wrap_profile_rate_stream(_response, st.profile_rate_admission, _v2_plan)
            _profile_rate_streamed = True

        # Streaming lifecycle: the outermost wrapper is the single owner of
        # the admission slot and releases it exactly once when the body
        # ends (drained, disconnect, upstream error) (#2403 item 2).
        if st.admission_ticket is not None and isinstance(_response, StreamingResponse):
            _response = wrap_stream_finally(_response, st.admission_ticket.release)
            _admission_streamed = True
            st.admission_ticket.defer()
        if _audit_request_id:
            _response.headers["X-Conduct-Request-Id"] = str(_audit_request_id)
        return _response
    except FederationDenied as error:
        from app.modules.auth.federation.gateway import error_response
        return error_response(error)
    finally:
        if st.profile_rate_admission is not None and not _profile_rate_streamed:
            from app.modules.guard.gateway_profile_rate_limit import finish_profile_rate_limit
            await finish_profile_rate_limit(st.profile_rate_admission, st.v2_plan)
        # Outer admission cleanup on every non-streaming exit path. A
        # streamed ticket is released once by wrap_stream_finally above.
        if st.admission_ticket is not None and not _admission_streamed:
            try:
                if not st.admission_ticket.released:
                    await st.admission_ticket.release()
            except Exception:
                pass
