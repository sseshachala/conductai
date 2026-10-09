"""Gateway v2 stream wrappers — finalize, receipt correlation, and the
legacy audit-record wrapper applied to streaming responses.

Split out of ``gateway_handler.py``; re-exported there."""
from __future__ import annotations

import asyncio
import time

import structlog
from fastapi.responses import StreamingResponse


log = structlog.get_logger("app.modules.guard.gateway_handler")


async def _close_stream_iterator(iterator):
    from anyio import CancelScope
    close = getattr(iterator, "aclose", None)
    if close:
        with CancelScope(shield=True):
            try:
                await close()
            except Exception:
                log.warning("gateway.v2.stream_close_failed")


def _wrap_v2_stream_finalize(
    response: StreamingResponse,
    *,
    on_close=None,
    durable=None,
    row_id,
    workspace_id: str,
    provider: str,
    model: str,
    # #2403 item 6: ``model`` is the served model; the client-facing
    # alias (cond-...) rides on receipts as ``model_alias``.
    model_alias: str | None = None,
    # P1-4: real request path (e.g. /gateway/v1/openai/v1/responses) — the
    # production caller (``handle_gateway_request``) always passes
    # ``request.url.path`` so the normalizer picks the right family
    # (Responses vs Chat). Default is only for legacy test scaffolding;
    # a source-string pin in tests/runtime/accounting/test_pr4_settlement_cutover
    # asserts the handler passes an explicit operation on both call sites.
    operation: str = "chat.completions.stream",
    body: dict,
    ingress_decision: str,
    ingress_rule_id: str | None,
    routing_meta: dict | None,
    clerk_user_id: str | None,
    ai_tool: str | None,
    user_email: str | None,
    started_monotonic: float,
    stream_deadline_seconds: float | None = None,
    # #2209 Session 6D — for accounting shadow write attribution.
    conductai_run_id: str | None = None,
    hook_session_id: str | None = None,
    agent_identity_id: str | None = None,
    # R4 fix (reviewer P1): reservation ownership transferred from the
    # handler. Wrapper computes actual_cents from the drained body then
    # calls settle_reservations on stream close / cancel / timeout.
    reservations: list | None = None,
    _routing_meta: dict | None = None,
    # #2173 P1 — stream-gate outcome. Wrapper reads this after the
    # stream drains to decide the audit decision + execution_status.
    # None = tool-gate was not applied; finalize uses upstream signals only.
    tool_stream_outcome=None,
    upstream_capture: bytearray | None = None,
) -> StreamingResponse:
    """Fire durable-audit finalize when the streaming response closes.

    Collects bytes as they pass through so the audit row records the full
    upstream body for cost + token accounting. Non-streaming v2 does its
    finalize synchronously in ``handle_gateway_request``; for streaming
    the finalize *has to* wait until the stream drains, which is why
    this wrapper exists.

    X4 — stream lifetime:

    - ``durable``: the ``DurableRow`` from ``open_durable_row()``, whose
      renewal task keeps the audit row's lease alive. The handler stops
      cancelling it in its own ``finally``; this wrapper cancels it
      here AFTER finalize completes so the row stays leased for the
      full stream body, not just the header-arrival window.
    - ``stream_deadline_seconds``: wall-clock cap from the profile's
      ``timeout_seconds``. The coordinator's ``wait_for`` only guarded
      header arrival; without a body-side deadline a stalled vendor
      stream could hold the connection open indefinitely. If exceeded,
      raise ``asyncio.TimeoutError`` — the outer ``finally`` records
      it as ``execution_status='error'`` and cancels renewal.

    Upstream capture precedes conversion and tool redaction. Accounting
    consumes vendor usage, not the rewritten frames delivered to clients.
    """
    import asyncio as _a

    original = response.body_iterator

    async def _wrapped():
        collected = bytearray()
        stream_exc: BaseException | None = None
        # Y3 — the original ``async for chunk in original`` implicitly
        # awaits ``__anext__``. That await has no timeout of its own,
        # so a stalled upstream (headers arrived, then no chunk ever
        # sent) blocks here indefinitely — the profile's
        # ``timeout_seconds`` is only checked BEFORE each chunk yields.
        # Reviewer's reproducer: a mock body_iterator whose
        # ``__anext__`` sleeps past the deadline never trips the check.
        #
        # Fix: drive the iteration by hand, ``wait_for(anext)`` with
        # the remaining budget as the timeout. TimeoutError from
        # wait_for lands in the outer except and finalize records
        # ``execution_status='timeout'``.
        iterator = original.__aiter__() if hasattr(original, "__aiter__") else original
        try:
            while True:
                if stream_deadline_seconds is not None:
                    remaining = stream_deadline_seconds - (
                        time.monotonic() - started_monotonic
                    )
                    if remaining <= 0:
                        raise _a.TimeoutError(
                            f"stream body exceeded profile "
                            f"timeout_seconds={stream_deadline_seconds}"
                        )
                    try:
                        chunk = await _a.wait_for(
                            iterator.__anext__(), timeout=remaining,
                        )
                    except _a.TimeoutError:
                        # Re-raise with our message so the finalize
                        # branch below distinguishes stalled-upstream
                        # timeout from other timeouts.
                        raise _a.TimeoutError(
                            f"stream body exceeded profile "
                            f"timeout_seconds={stream_deadline_seconds}"
                            f" (stalled upstream)"
                        )
                else:
                    try:
                        chunk = await iterator.__anext__()
                    except StopAsyncIteration:
                        break
                if isinstance(chunk, str):
                    chunk_bytes = chunk.encode("utf-8")
                else:
                    chunk_bytes = chunk
                collected.extend(chunk_bytes)
                yield chunk_bytes
        except StopAsyncIteration:
            pass
        except BaseException as exc:  # noqa: BLE001 — need CancelledError too
            stream_exc = exc
            raise
        finally:
            await _close_stream_iterator(original)
            from app.modules.guard.gateway_lifecycle import (
                close_durable_row as _close_durable,
                finalize_durable_row as _finalize_durable_row,
            )
            _is_cancel = isinstance(stream_exc, _a.CancelledError)
            _is_timeout = isinstance(stream_exc, _a.TimeoutError)
            _decision = ingress_decision if stream_exc is None else "error"
            if stream_exc is None:
                _execution_status = "ok"
            elif _is_cancel:
                _execution_status = "interrupted"
            elif _is_timeout:
                _execution_status = "timeout"
            else:
                _execution_status = "error"
            _result_summary = (
                None
                if stream_exc is None
                else (
                    "Stream cancelled by client" if _is_cancel
                    else (
                        f"Stream body exceeded {stream_deadline_seconds}s "
                        f"wall-clock deadline" if _is_timeout
                        else f"stream aborted: {type(stream_exc).__name__}: {str(stream_exc)[:400]}"
                    )
                )
            )
            # #2173 P1 — stream-gate outcome takes precedence over the
            # "no exception raised = ok" default. A synthetic error
            # frame from tools_stream_gate does NOT raise (the stream
            # completed normally from the ASGI side), so without this
            # override the audit row landed as decision=allowed
            # execution_status=ok despite the client seeing an error.
            _final_routing_meta = routing_meta
            _final_rule_id = ingress_rule_id
            _final_result_summary = _result_summary
            if stream_exc is None and tool_stream_outcome is not None:
                try:
                    from app.modules.guard.tools_stream_gate import (
                        StreamGateStatus as _SGS,
                    )
                    from app.modules.guard.tools_validator import (
                        ResponseGateReason as _RGR,
                    )
                    _st = tool_stream_outcome.status
                    if _st != _SGS.OK:
                        # Any non-OK stream-gate verdict → blocked row.
                        _decision = "blocked"
                        _execution_status = "error"
                        _final_result_summary = (
                            tool_stream_outcome.reason or _st.value
                        )
                        # Map to the same response_gate_reason taxonomy
                        # as non-streaming so audit UI can label alike.
                        if _st == _SGS.POLICY_BLOCK:
                            _reason_val = _RGR.POLICY_BLOCK
                            _final_rule_id = (
                                tool_stream_outcome.reason
                                or "guard.stream.policy_block"
                            )
                        else:
                            _reason_val = _RGR.VALIDATION_FAILURE
                            _final_rule_id = (
                                f"guard.stream.{_st.value}"
                            )
                        _final_routing_meta = {
                            **(routing_meta or {}),
                            "response_gate_reason": _reason_val,
                            "stream_gate_status": _st.value,
                        }
                    if tool_stream_outcome.correlation_ids:
                        _final_routing_meta = {
                            **(_final_routing_meta or {}),
                            "tool_call_correlation_ids": (
                                tool_stream_outcome.correlation_ids
                            ),
                        }
                except Exception:
                    log.exception(
                        "guard.gateway.stream_outcome_merge_failed",
                        row_id=row_id,
                    )
            try:
                await _finalize_durable_row(
                    row_id=row_id,
                    workspace_id=workspace_id,
                    decision=_decision,
                    provider=provider,
                    model=model,
                    body=body,
                    response_bytes=bytes(upstream_capture if upstream_capture is not None else collected) or None,
                    duration_ms=int((time.monotonic() - started_monotonic) * 1000),
                    rule_id=_final_rule_id,
                    routing_meta=_final_routing_meta,
                    execution_status=_execution_status,
                    result_summary=_final_result_summary,
                    clerk_user_id=clerk_user_id,
                    ai_tool=ai_tool,
                    user_email=user_email,
                )
            except Exception:
                log.exception(
                    "guard.gateway.v2.stream_finalize_failed",
                    row_id=row_id,
                )
            # R4 fix (reviewer P1): settle reservations from the
            # drained upstream body. Runs on success, cancel, and
            # timeout — same finally as finalize.
            _stream_resp_bytes = bytes(upstream_capture if upstream_capture is not None else collected) or None
            _stream_new_engine_micros: int | None = None
            if (
                _stream_resp_bytes is not None
                and (_routing_meta or {}).get("billable", True) is not False
            ):
                try:
                    from app.runtime.accounting.settlement import (
                        settle_micros_for_attempts,
                    )
                    _stream_attempts_for_settle = (
                        _routing_meta.get("attempts")
                        if isinstance(_routing_meta, dict)
                        else None
                    )
                    _stream_new_engine_micros = settle_micros_for_attempts(
                        attempts_meta=_stream_attempts_for_settle,
                        request_provider=provider,
                        request_model=model,
                        operation=operation,  # P1-4: real path picks the right family
                        winner_response_bytes=_stream_resp_bytes,
                        strict=True,
                    )
                except Exception:
                    log.exception(
                        "guard.gateway.v2.stream_settle_compute_failed",
                        row_id=row_id,
                        provider=provider,
                        model=model,
                    )
            # P1-D (post-review): persist per-attempt receipts BEFORE
            # settling reservations. Same ordering invariant as the
            # non-streaming path. Failure to persist any expected receipt
            # ⇒ skip settle; recovery sweep reconstructs from whatever
            # eventually lands.
            _stream_receipts_durable = False
            _stream_meta = _routing_meta if isinstance(_routing_meta, dict) else {}
            _stream_attempts_meta = _stream_meta.get("attempts")
            _stream_expected_receipts = (
                len(_stream_attempts_meta) if _stream_attempts_meta else 1
            )
            try:
                from app.runtime.accounting.shadow_writer import (
                    write_receipts_for_attempts as _write_shadow_attempts,
                )
                from starlette.concurrency import (
                    run_in_threadpool as _rin_threadpool_shadow,
                )
                _reserved_micros: int | None = None
                if reservations:
                    try:
                        _reserved_micros = sum(
                            int(getattr(r, "estimated_micros", 0) or 0)
                            for r in reservations
                        ) or None
                    except Exception:
                        _reserved_micros = None
                # #2209 Session 6D — workflow attribution.
                _stream_wf_run_uuid = None
                if conductai_run_id:
                    try:
                        import uuid as _uuid_wf_stream
                        _stream_wf_run_uuid = _uuid_wf_stream.UUID(
                            str(conductai_run_id)
                        )
                    except (ValueError, TypeError):
                        _stream_wf_run_uuid = None
                _stream_receipt_ids = await _rin_threadpool_shadow(
                    _write_shadow_attempts,
                    workspace_id=workspace_id,
                    request_id=(
                        (durable.request_id if durable is not None else None)
                        or row_id
                    ),
                    provider=provider,
                    model=model,
                    model_alias=model_alias,
                    operation=operation,  # P1-4: real op flows to receipt normalizer too
                    dispatched=True,
                    response_bytes=_stream_resp_bytes,
                    reserved_microdollars=_reserved_micros,
                    developer_external_id=clerk_user_id,
                    source="gateway",
                    client_tool=ai_tool,
                    attempts_meta=_stream_attempts_meta,
                    workflow_run_id=_stream_wf_run_uuid,
                    hook_session_id=hook_session_id,
                    agent_identity_id=agent_identity_id,
                )
                _stream_receipts_durable = (
                    _stream_receipt_ids is not None
                    and len(_stream_receipt_ids) >= _stream_expected_receipts
                )
                if not _stream_receipts_durable:
                    log.warning(
                        "guard.gateway.v2.stream_receipts_partial_skip_settle",
                        row_id=row_id,
                        written=(
                            len(_stream_receipt_ids)
                            if _stream_receipt_ids else 0
                        ),
                        expected=_stream_expected_receipts,
                    )
            except Exception:
                log.exception(
                    "guard.gateway.v2.stream_receipts_write_failed",
                    row_id=row_id,
                )
                _stream_receipts_durable = False

            if reservations and _stream_receipts_durable:
                try:
                    from app.modules.guard.gateway_lifecycle import (
                        settle_reservations as _settle_reservations,
                    )
                    from app.core.database import SessionLocal
                    _dispatched_stream = True
                    _actual_cents_stream: int | None = None
                    _actual_micros_stream: int | None = None
                    if _stream_new_engine_micros is not None:
                        _actual_micros_stream = _stream_new_engine_micros
                        _actual_cents_stream = int(round(_stream_new_engine_micros / 10_000))
                    # R3 pattern: offload the sync settle to a threadpool
                    # so the ASGI drain path stays responsive.
                    def _settle_stream_owned():
                        _db = SessionLocal()
                        try:
                            _settle_reservations(
                                db=_db,
                                reservations=reservations,
                                dispatched=_dispatched_stream,
                                actual_cents=_actual_cents_stream,
                                actual_micros=_actual_micros_stream,
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
                    from starlette.concurrency import (
                        run_in_threadpool as _rin_threadpool,
                    )
                    await _rin_threadpool(_settle_stream_owned)
                except Exception:
                    log.exception(
                        "guard.gateway.v2.stream_settle_failed",
                        row_id=row_id,
                        reservation_count=len(reservations) if reservations else 0,
                    )

            # X4 — cancel the renewal task last, AFTER finalize. If we
            # cancelled first, the row would show up as expired to the
            # reconciler in the seconds between cancellation and
            # finalize completion.
            if durable is not None:
                try:
                    await _close_durable(durable)
                except Exception:
                    log.exception(
                        "guard.gateway.v2.stream_close_durable_failed",
                        row_id=row_id,
                    )
            if on_close is not None:
                try:
                    if asyncio.iscoroutinefunction(on_close):
                        await on_close()
                    else:
                        on_close()
                except Exception:
                    log.warning("guard.gateway.v2.stream_on_close_failed")

    return StreamingResponse(
        _wrapped(),
        media_type=response.media_type,
        headers=dict(response.headers),
        status_code=response.status_code,
    )


def _wrap_stream_receipts(response: StreamingResponse, *, upstream_capture=None, **receipt_args) -> StreamingResponse:
    """Persist legacy/audit-off stream receipts after usage arrives, including disconnects."""
    original = response.body_iterator

    async def chunks():
        from anyio import CancelScope
        from starlette.concurrency import run_in_threadpool
        from app.runtime.accounting.shadow_writer import write_receipts_for_attempts
        collected = bytearray()
        outcome = "succeeded"
        try:
            async for chunk in original:
                data = chunk.encode() if isinstance(chunk, str) else chunk
                collected.extend(data)
                yield data
        except BaseException as exc:
            outcome = "disconnected" if isinstance(exc, (asyncio.CancelledError, GeneratorExit)) else "failed"
            raise
        finally:
            with CancelScope(shield=True):
                close = getattr(original, "aclose", None)
                if close is not None:
                    try:
                        await close()
                    except Exception:
                        log.exception("guard.gateway.stream_close_failed", request_id=receipt_args.get("request_id"))
                try:
                    await run_in_threadpool(write_receipts_for_attempts, **receipt_args,
                                            dispatched=True, response_bytes=bytes(upstream_capture if upstream_capture is not None else collected) or None,
                                            winner_execution_outcome=outcome)
                except Exception:
                    log.exception("guard.gateway.stream_receipts_failed", request_id=receipt_args.get("request_id"))

    response.body_iterator = chunks()
    return response


def _wrap_v2_stream_record_legacy(
    response: StreamingResponse,
    *,
    on_close=None,
    background,
    workspace_id: str,
    clerk_user_id: str | None,
    ai_tool: str | None,
    provider: str,
    model: str,
    body: dict,
    prompt_summary: str,
    user_email: str | None,
    conductai_run_id,
    conductai_workflow,
    conductai_workflow_id,
    hook_session_id,
    routing_meta: dict | None,
    agent_identity_id: str | None,
    route: str,
    ingress_decision: str,
    ingress_rule_id: str | None,
    started_monotonic: float,
    record_audit_fn,
    tool_stream_outcome=None,
    upstream_capture: bytearray | None = None,
    request_id: str | None = None,
    stream_deadline_seconds: float | None = None,
) -> StreamingResponse:
    """X2 fallback wrapper — mirrors ``_wrap_v2_stream_finalize`` but
    schedules ``_record_audit`` (v1's single-phase writer) instead of
    ``_finalize_durable_row``. Used when v2 executes but the
    durable-audit canary is off for this workspace.

    Same shape guarantees: collects bytes as they pass, fires the
    audit call on stream close (or cancellation), never swallows the
    stream on writer failure.

    Z2 — deadline enforcement is now independent of the audit flag.
    ``stream_deadline_seconds`` uses the same ``asyncio.wait_for``
    per-chunk pattern as ``_wrap_v2_stream_finalize`` (Y3 fix), so a
    stalled upstream trips the profile timeout whether durable-audit
    is on or off. Prior state: only the durable-on wrapper enforced
    the deadline → stalled streams under durable-off held the
    connection open indefinitely.
    """
    import asyncio as _a

    original = response.body_iterator

    async def _wrapped():
        collected = bytearray()
        stream_exc: BaseException | None = None
        iterator = (
            original.__aiter__() if hasattr(original, "__aiter__") else original
        )
        try:
            # Z2 — same per-chunk wait_for pattern as Y3 uses in the
            # durable-on wrapper. Refactoring both wrappers to share
            # the loop would be nicer, but keeping them side-by-side
            # for review clarity: the shape MUST match so a future
            # fix to one is easy to mirror.
            while True:
                if stream_deadline_seconds is not None:
                    remaining = stream_deadline_seconds - (
                        time.monotonic() - started_monotonic
                    )
                    if remaining <= 0:
                        raise _a.TimeoutError(
                            f"stream body exceeded profile "
                            f"timeout_seconds={stream_deadline_seconds}"
                        )
                    try:
                        chunk = await _a.wait_for(
                            iterator.__anext__(), timeout=remaining,
                        )
                    except _a.TimeoutError:
                        raise _a.TimeoutError(
                            f"stream body exceeded profile "
                            f"timeout_seconds={stream_deadline_seconds}"
                            f" (stalled upstream)"
                        )
                else:
                    try:
                        chunk = await iterator.__anext__()
                    except StopAsyncIteration:
                        break
                if isinstance(chunk, str):
                    chunk_bytes = chunk.encode("utf-8")
                else:
                    chunk_bytes = chunk
                collected.extend(chunk_bytes)
                yield chunk_bytes
        except StopAsyncIteration:
            pass
        except BaseException as exc:  # noqa: BLE001
            stream_exc = exc
            raise
        finally:
            await _close_stream_iterator(original)
            _is_cancel = isinstance(stream_exc, _a.CancelledError)
            _is_timeout = isinstance(stream_exc, _a.TimeoutError)
            _decision = ingress_decision if stream_exc is None else "error"
            if stream_exc is None:
                _execution_status = "success"
            elif _is_cancel:
                _execution_status = "interrupted"
            elif _is_timeout:
                _execution_status = "timeout"
            else:
                _execution_status = "error"
            if stream_exc is None and tool_stream_outcome is not None:
                from app.modules.guard.tools_stream_gate import StreamGateStatus
                if tool_stream_outcome.status != StreamGateStatus.OK:
                    _decision = "blocked"
                    _execution_status = "error"
                    ingress_rule = tool_stream_outcome.reason or tool_stream_outcome.status.value
                    final_routing_meta = {**(routing_meta or {}),
                                    "stream_gate_status": tool_stream_outcome.status.value,
                                    "response_gate_reason": "policy_block" if tool_stream_outcome.status == StreamGateStatus.POLICY_BLOCK else "validation_failure"}
                else:
                    ingress_rule = ingress_rule_id
                    final_routing_meta = routing_meta
            else:
                ingress_rule = ingress_rule_id
                final_routing_meta = routing_meta
            if tool_stream_outcome is not None and tool_stream_outcome.correlation_ids:
                final_routing_meta = {**(final_routing_meta or {}), "tool_call_correlation_ids": tool_stream_outcome.correlation_ids}
            try:
                # Z1 note — same failure mode as the non-streaming
                # exception path: background.add_task never runs if
                # the response was aborted. Streaming's "response
                # already sent" state means ASGI does drain queued
                # tasks in the happy path; on error, this may or may
                # not fire depending on ASGI server timing. Not
                # worth switching to asyncio.to_thread here because
                # the stream completed the send BEFORE this finally
                # (bytes were yielded successfully); the writer
                # timing is a best-effort observability signal, not
                # a correctness gate.
                background.add_task(
                    record_audit_fn,
                    workspace_id, clerk_user_id, ai_tool, provider, model,
                    _decision,
                    ingress_rule,
                    int((time.monotonic() - started_monotonic) * 1000),
                    body=body,
                    response_bytes=bytes(upstream_capture if upstream_capture is not None else collected) or None,
                    prompt_summary=prompt_summary,
                    user_email=user_email,
                    conductai_run_id=conductai_run_id,
                    conductai_workflow=conductai_workflow,
                    conductai_workflow_id=conductai_workflow_id,
                    hook_session_id=hook_session_id,
                    routing_meta=final_routing_meta,
                    execution_status=_execution_status,
                    agent_identity_id=agent_identity_id,
                    route=route,
                    request_id=request_id,
                )
            except Exception:
                log.exception(
                    "guard.gateway.v2.stream_record_legacy_failed",
                    workspace_id=workspace_id,
                )
            if on_close is not None:
                try:
                    if asyncio.iscoroutinefunction(on_close):
                        await on_close()
                    else:
                        on_close()
                except Exception:
                    log.warning("guard.gateway.v2.stream_on_close_failed")

    return StreamingResponse(
        _wrapped(),
        media_type=response.media_type,
        headers=dict(response.headers),
        status_code=response.status_code,
    )
