"""Gateway lifecycle phase 8: receipts → settlement, non-streaming (#2399).

Extracted verbatim from the ``finally`` of ``handle_gateway_request``'s
forward block. This is the LIVE-WRITE settlement surface; the other two
(Redis rebuild and the stale-reservation recovery sweep) read the same
receipts. Order is load-bearing (P1-D): price every attempt, persist the
per-attempt receipts, and settle reservations only when every expected
receipt is durable. Streaming responses skip this: the stream wrapper
owns receipts + settlement after the body drains (R4).
"""
from __future__ import annotations

import structlog
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.modules.guard.gateway_attempt_outcome import served_model as _served_model
from app.modules.guard.gateway_request_state import GatewayCall

log = structlog.get_logger(__name__)


async def settle_request(
    st: GatewayCall,
    *,
    _dispatched: bool,
    _response,
    _v2_upstream_body_bytes: bytes | None,
    _routing_meta: dict | None,
) -> None:
    """Idempotent + best-effort; every failure is logged, never raised."""
    from app.core.database import SessionLocal
    from app.modules.guard.gateway_lifecycle import settle_reservations as _settle_reservations

    request, workspace_id, provider, model = st.request, st.workspace_id, st.provider, st.model
    _reservations = st.reservations
    _actual_cents: int | None = None
    _actual_micros: int | None = None  # R9 (reviewer P1)
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
            if st.run_id:
                try:
                    import uuid as _uuid_wf
                    _wf_run_uuid = _uuid_wf.UUID(str(st.run_id))
                except (ValueError, TypeError):
                    _wf_run_uuid = None
            _receipt_ids = await run_in_threadpool(
                _write_shadow_attempts,
                workspace_id=workspace_id,
                request_id=st.audit_request_id,
                provider=provider,
                model=_served_model(_routing_meta, model), model_alias=(model if st.v2_plan is not None else None),
                operation=request.url.path,
                dispatched=_dispatched,
                response_bytes=_resp_bytes,
                reserved_microdollars=_reserved_micros,
                developer_external_id=st.clerk_user_id,
                agent_identity_id=st.agent_identity_id,
                source="gateway",
                client_tool=st.ai_tool,
                attempts_meta=_attempts_meta,
                workflow_run_id=_wf_run_uuid,
                hook_session_id=st.hook_session_id,
            )
            _receipts_durable = (
                _receipt_ids is not None
                and len(_receipt_ids) >= _expected_receipts
            )
            if not _receipts_durable:
                log.warning(
                    "guard.gateway.receipts_partial_skip_settle",
                    request_id=str(st.audit_request_id),
                    written=len(_receipt_ids) if _receipt_ids else 0,
                    expected=_expected_receipts,
                )
        except Exception:
            log.exception(
                "guard.gateway.receipts_write_failed",
                request_id=str(st.audit_request_id),
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
