"""Canonical Gateway request entry point.

Owns the full Gateway request lifecycle: authenticate the caller (member
token, agent identity, or run token), evaluate Guard policies, open a
durable-audit row via ``gateway_lifecycle``, forward to the vendor, apply
the response gate, and close the audit row. Legacy ``/proxy/*`` route
decorators in ``routers/proxy.py`` delegate here — no new Gateway behavior
is allowed to grow on that legacy surface.
"""
from __future__ import annotations

import asyncio
import time

from starlette.concurrency import run_in_threadpool
import uuid

import structlog
from fastapi import BackgroundTasks, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import text

from app.core.config import settings
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
    # Helpers live in gateway_helpers.py (extracted 2026-09-17). Re-exports
    # come from their real home modules. routers/proxy.py is legacy and this
    # handler no longer depends on it.
    from app.core.auth import resolve_agent_token, token_is_expired
    from app.core.database import SessionLocal
    from app.core.workspace_context import set_workspace_rls
    from app.runtime.provider_transport import get_provider_transport_registry
    from app.guard.audit import record as _record_audit
    from app.runtime.accounting.estimator import estimate_tokens as _estimate_tokens
    from app.guard.policy import flatten_prompt as _flatten_prompt
    from app.guard.router import fail_closed as _fail_closed, upstream as _forward
    from app.modules.guard.gateway_helpers import (
        _apply_response_gate,
        _apply_tier_resolution,
        _apply_tier_resolution_owned,
        _extract_member_token,
        _infer_ai_tool,
        _inject_guidance,
        _redact_body,
        _resolve_gateway_auth,
        _upstream_api_key,
        _upstream_url,
        _vault_key,
        _wrap_streaming_response,
    )
    from app.modules.guard.gateway_attempt_outcome import merge_attempts as _merge_attempts  # #2403
    from app.modules.guard.gateway_attempt_outcome import served_model as _served_model, wrap_stream_finally
    from app.modules.guard import gateway_phase_ingress as _ingress
    from app.modules.guard import gateway_phase_routing as _routing
    from app.modules.guard import gateway_phase_policy as _policy
    from app.modules.guard import gateway_phase_upstream as _upstream
    from app.modules.guard import gateway_phase_reserve as _reserve
    from app.modules.guard import gateway_phase_dispatch as _dispatch
    from app.modules.guard import gateway_phase_finalize as _finalize

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

    # PR 2 (#2056) admission state — kill switch: ADMISSION_ENABLED.
    _admission_ticket = None
    _admission_streamed = False
    _profile_rate_admission = None
    _profile_rate_streamed = False
    _v2_plan = None

    try:
        # 2. Identity → federation → admission acquire (gateway_phase_ingress).
        if (_early := await _ingress.resolve_caller(st, operation=operation)) is not None:
            return _early
        workspace_id, clerk_user_id = st.workspace_id, st.clerk_user_id
        _agent_identity_id, _agent_risk_tier = st.agent_identity_id, st.agent_risk_tier
        _federation, _admission_ticket = st.federation, st.admission_ticket
        from app.modules.auth.federation.gateway import recheck_gateway

        # 3. Body → model routing → v2 plan (gateway_phase_routing).
        _early = await _routing.parse_and_route(st, build_v2_plan_owned=_build_v2_plan_owned)
        _v2_plan = st.v2_plan
        if _early is not None:
            return _early
        body, model, _routing_meta, ai_tool = st.body, st.model, st.routing_meta, st.ai_tool
        _tools_offered, _tool_names_supplied = st.tools_offered, st.tool_names_supplied

        # 4a/4b. User email, workflow-run headers, trial plan.
        await _routing.load_request_context(st)
        _user_email, _run_id, _workflow, _workflow_id = st.user_email, st.run_id, st.workflow, st.workflow_id
        _environment_id, _hook_session_id, _is_trial = st.environment_id, st.hook_session_id, st.is_trial

        # 4c. Prompt gate → rate limit (gateway_phase_policy).
        if (_early := await _policy.evaluate_prompt_gate(st)) is not None:
            return _early
        prompt_summary, decision, _guidance_text = st.prompt_summary, st.decision, st.guidance_text
        _audit_decision, _audit_rule_id = st.audit_decision, st.audit_rule_id
        _early = await _policy.check_rate_limits(st)
        _profile_rate_admission = st.profile_rate_admission
        if _early is not None:
            return _early

        # 5–6. v1 credentials → outbound body/headers (gateway_phase_upstream).
        if (_early := await _upstream.resolve_upstream_credentials(st)) is not None:
            return _early
        _upstream.prepare_outbound_request(st)
        upstream, _upstream_key, _vault_key_val = st.upstream, st.upstream_key, st.vault_key_val
        transport, real_key, body = st.transport, st.real_key, st.body
        is_stream, extra_headers = st.is_stream, st.extra_headers
        _client_request_id, _routing_meta = st.client_request_id, st.routing_meta

        # 7. Durable acceptance → budget reservation (gateway_phase_reserve).
        if (_early := await _reserve.open_audit_and_reserve(st)) is not None:
            return _early
        from app.modules.guard.gateway_lifecycle import (
            close_durable_row as _close_durable,
            finalize_durable_row as _finalize_durable_row,
            settle_reservations as _settle_reservations,
        )
        _durable, _durable_row_id = st.durable, st.durable_row_id
        _audit_request_id, _reservations = st.audit_request_id, st.reservations
        _dispatched = False  # flipped to True right before any upstream call
        _actual_cents: int | None = None
        _actual_micros: int | None = None  # R9 (reviewer P1)

        # P1: forward + response-gate must run under an exception-safe
        # lifecycle. Prior structure had close_durable_row *after* the
        # gate block, so any exception (or cancellation) between here and
        # the close call leaked the whole-request heartbeat: the renewal
        # task kept renew_lease-ing an abandoned row forever, preventing
        # the reconciler from ever flipping it. Guarantees now:
        #   - close_durable_row runs on every exit path (finally).
        #   - On exception, best-effort finalize with 'error' / 'interrupted'
        #     so the row lands terminated immediately instead of waiting on
        #     the reconciler's lease-expiry sweep.
        import asyncio as _asyncio
        # X4 — set before the try/finally so ``finally: _close_durable``
        # can read it even if an early raise skips the wrap.
        _v2_stream_wrapped = False
        _tool_stream_outcome = None  # set inside the streaming tool-gate branch
        # Same reason — the finally block down at ~line 1374 references
        # ``_response`` when computing actuals for settle. Any raise
        # inside the try (v2 502 from _execute_v2, v1 forwarder error,
        # etc.) leaves the assignment unbound and Python raises
        # UnboundLocalError from the finally, masking the real
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
                    plan=_v2_plan, body=body, stream=is_stream,
                    policy_check=_policy_check,
                    client_headers=_v2_client_headers,
                )
                # Reflect coordinator attempt records back into routing_meta
                # so the durable audit row lands with the full attempt list.
                _routing_meta = _merge_routing_meta(_routing_meta, _v2_plan.last_meta)
                _v2_upstream_body_bytes = _dispatch.v2_upstream_snapshot(_response, _v2_plan)
            else:
                # ── PR-A2b: dispatch boundary (legacy path) ──
                await run_in_threadpool(recheck_gateway, _federation)
                _dispatched = True
                _response = await _dispatch.forward_v1(st)
            # #2159 PR 2 — scan tool_call arguments BEFORE the composed-
            # engine gate (RedactionFailure → 502 terminal, redacted body
            # substituted otherwise, routing_meta updated).
            if (
                operation == "inference"
                and not is_stream
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
                # durable-audit off wrote ZERO rows (reviewer's
                # ``recorded 0 times`` reproducer).
                #
                # Fix: run ``_record_audit`` synchronously in a thread
                # (``asyncio.to_thread``) BEFORE re-raising. Blocks the
                # exception path by the DB write duration, but that's
                # bounded by audit.record's own timeout and it's the only
                # way the row lands. Failure of the writer itself is
                # logged, never re-raised, so the original exception the
                # caller sees is preserved.
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
            # ``_wrap_v2_stream_finalize``. Cancelling here would kill the
            # lease before ASGI consumes the body; the reconciler would
            # flip a live stream to orphaned. The wrapper's ``finally``
            # calls ``_close_durable`` after the stream drains.
            #
            # For every other exit path (non-streaming, error, cancel
            # before we ever wrapped), cancel here — idempotent.
            if not _v2_stream_wrapped:
                await _close_durable(_durable)

            # ── PR-A2b: settle reservations ────────────────────────
            # Idempotent + best-effort. Empty list is a NOOP (matches
            # ACCEPTED_NO_HARD_CAP / DISABLED). See helper docstring for
            # the dispatched x actual_cents truth table.
            # R4 fix (reviewer P1): for streaming responses the stream
            # wrapper (``_wrap_v2_stream_finalize``) owns settlement so
            # actual_cents reflects the drained body. Skip inline here
            # to avoid settling twice.
            # #2209 review #2 (#2221): compute cost OUTSIDE the reservation
            # gate so per-attempt receipts fire for every settled attempt,
            # not just reserved ones.
            _resp_bytes: bytes | None = None
            _new_engine_micros: int | None = None
            if _dispatched and not isinstance(_response, StreamingResponse):  # None = all attempts failed
                _snapshot = locals().get("_v2_upstream_body_bytes")
                if isinstance(_snapshot, (bytes, bytearray)) and _snapshot:
                    _resp_bytes = bytes(_snapshot)
                elif _response is not None and hasattr(_response, "body"):
                    try:
                        _resp_bytes = _response.body
                    except Exception:
                        _resp_bytes = None
                if (_resp_bytes is not None or (_routing_meta or {}).get("attempts")) and (_routing_meta or {}).get("billable", True) is not False:
                    try:
                        from app.runtime.accounting.settlement import (
                            settle_micros_for_attempts,
                        )
                        _attempts_for_settle = (
                            _routing_meta.get("attempts")
                            if isinstance(_routing_meta, dict)
                            else None
                        )
                        # P1-2: sum per-attempt priced micros using each
                        # attempt's actual provider/model + captured bytes.
                        # Falls back to winner-only when no attempts_meta.
                        _new_engine_micros = settle_micros_for_attempts(
                            attempts_meta=_attempts_for_settle,
                            request_provider=provider,
                            request_model=model,
                            operation=request.url.path,
                            winner_response_bytes=_resp_bytes,
                            strict=True,
                        )
                    except Exception:
                        log.exception(
                            "guard.gateway.settle_compute_failed",
                            workspace_id=str(workspace_id),
                            provider=provider,
                            model=model,
                        )

            # P1-D (post-review): persist per-attempt receipts BEFORE
            # settling reservations. Receipts are the durable, idempotent
            # authoritative record recovery reads (P1-1, P1-A). Settling
            # first and losing the write leaves committed spend with no
            # evidence to reconstruct from. Failure to persist any
            # expected receipt ⇒ skip settle; the reservation stays open
            # and the recovery sweep re-classifies from the receipt(s)
            # that eventually land.
            _receipts_durable = False
            _attempts_meta = (
                _routing_meta.get("attempts")
                if isinstance(_routing_meta, dict)
                else None
            )
            _expected_receipts = (
                len(_attempts_meta) if _attempts_meta else 1
            )
            if not isinstance(_response, StreamingResponse):
                try:
                    from app.runtime.accounting.shadow_writer import (
                        write_receipts_for_attempts as _write_shadow_attempts,
                    )
                    _reserved_micros: int | None = None
                    if _reservations:
                        try:
                            _reserved_micros = sum(
                                int(getattr(r, "estimated_micros", 0) or 0)
                                for r in _reservations
                            ) or None
                        except Exception:
                            _reserved_micros = None
                    # #2209 Session 6D — attribution: when this Gateway
                    # request originated from a workflow run (brain_block
                    # via gateway_profile adapter), the caller sent
                    # x-conductai-run-id — carry it onto the receipt so
                    # per-run cost aggregations JOIN cleanly.
                    _wf_run_uuid = None
                    if _run_id:
                        try:
                            import uuid as _uuid_wf
                            _wf_run_uuid = _uuid_wf.UUID(str(_run_id))
                        except (ValueError, TypeError):
                            _wf_run_uuid = None
                    _receipt_ids = await run_in_threadpool(
                        _write_shadow_attempts,
                        workspace_id=workspace_id,
                        request_id=_audit_request_id,
                        provider=provider,
                        model=_served_model(_routing_meta, model), model_alias=(model if _v2_plan is not None else None),
                        operation=request.url.path,
                        dispatched=_dispatched,
                        response_bytes=_resp_bytes,
                        reserved_microdollars=_reserved_micros,
                        developer_external_id=clerk_user_id,
                        agent_identity_id=_agent_identity_id,
                        source="gateway",
                        client_tool=ai_tool,
                        attempts_meta=_attempts_meta,
                        workflow_run_id=_wf_run_uuid,
                        hook_session_id=_hook_session_id,
                    )
                    _receipts_durable = (
                        _receipt_ids is not None
                        and len(_receipt_ids) >= _expected_receipts
                    )
                    if not _receipts_durable:
                        log.warning(
                            "guard.gateway.receipts_partial_skip_settle",
                            request_id=str(_audit_request_id),
                            written=len(_receipt_ids) if _receipt_ids else 0,
                            expected=_expected_receipts,
                        )
                except Exception:
                    log.exception(
                        "guard.gateway.receipts_write_failed",
                        request_id=str(_audit_request_id),
                    )
                    _receipts_durable = False

            # Reservation-gated settlement — actual cost from the new engine.
            # Gated on ``_receipts_durable`` (P1-D): if the receipts didn't
            # persist, leave the reservation open so the recovery sweep can
            # reconstruct authoritative cost from the receipt(s) that
            # eventually land. Never commit spend without durable evidence.
            if (
                _reservations
                and not isinstance(_response, StreamingResponse)
                and _receipts_durable
            ):
                try:
                    if _dispatched and _actual_cents is None and _new_engine_micros is not None:
                        _actual_micros = _new_engine_micros
                        _actual_cents = int(round(_new_engine_micros / 10_000))
                    # R3 fix (reviewer P1): settle owns its own session
                    # inside a threadpool call.
                    _reservations_snapshot = list(_reservations)
                    _dispatched_snapshot = _dispatched
                    _actual_cents_snapshot = _actual_cents
                    _actual_micros_snapshot = _actual_micros  # R9

                    def _settle_sync_owned():
                        _db = SessionLocal()
                        try:
                            _settle_reservations(
                                db=_db,
                                reservations=_reservations_snapshot,
                                dispatched=_dispatched_snapshot,
                                actual_cents=_actual_cents_snapshot,
                                actual_micros=_actual_micros_snapshot,  # R9
                            )
                            try:
                                _db.commit()
                            except Exception:
                                pass
                        finally:
                            try:
                                _db.close()
                            except Exception:
                                pass
                    await run_in_threadpool(_settle_sync_owned)
                except Exception:
                    log.exception(
                        "guard.gateway.settle_wire_failed",
                        reservation_count=len(_reservations),
                        dispatched=_dispatched,
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

        if _profile_rate_admission is not None and isinstance(_response, StreamingResponse):
            from app.modules.guard.gateway_profile_rate_limit import wrap_profile_rate_stream
            _response = wrap_profile_rate_stream(_response, _profile_rate_admission, _v2_plan)
            _profile_rate_streamed = True

        # Streaming lifecycle: the outermost wrapper is the single owner of
        # the admission slot and releases it exactly once when the body
        # ends (drained, disconnect, upstream error) (#2403 item 2).
        if _admission_ticket is not None and isinstance(_response, StreamingResponse):
            _response = wrap_stream_finally(_response, _admission_ticket.release)
            _admission_streamed = True
            _admission_ticket.defer()
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
        if _admission_ticket is not None and not _admission_streamed:
            try:
                if not _admission_ticket.released:
                    await _admission_ticket.release()
            except Exception:
                pass
