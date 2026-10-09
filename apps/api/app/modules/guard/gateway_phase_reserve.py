"""Gateway lifecycle phase 5: durable acceptance → budget reservation (#2399).

Extracted verbatim from ``handle_gateway_request``. #2057 invariants 2
(budget reservation) and 3 (durable acceptance): the durable audit row
opens first (idempotency key = client ``X-Request-Id``, #2403), then
hard-cap budgets are reserved before dispatch. Any non-ACCEPTED outcome
finalizes the row as ``blocked`` with an outcome-specific rule id,
closes the renewal task, and returns the budget-block response.
"""
from __future__ import annotations

import time

import structlog
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.modules.guard.gateway_request_state import GatewayCall

log = structlog.get_logger(__name__)


async def open_audit_and_reserve(st: GatewayCall) -> JSONResponse | None:
    """#1959 durable audit open, then PR-A2b pre-flight budget reservation."""
    from app.core.database import SessionLocal
    from app.modules.guard.gateway_lifecycle import (
        open_durable_row as _open_durable,
        close_durable_row as _close_durable,
        finalize_durable_row as _finalize_durable_row,
    )

    workspace_id, clerk_user_id, ai_tool = st.workspace_id, st.clerk_user_id, st.ai_tool
    provider, model, body = st.provider, st.model, st.body
    _routing_meta, _user_email = st.routing_meta, st.user_email
    _agent_identity_id = st.agent_identity_id
    # #1959 durable audit lifecycle. All logic (insert_accepted +
    # fail-closed decision + whole-request renewal) lives in
    # gateway_lifecycle so new Gateway behavior never grows in the
    # legacy proxy.py file. The resulting row_id is threaded through the
    # v1 audit_args tuple at index 18.
    _durable = await _open_durable(
        workspace_id=workspace_id,
        clerk_user_id=clerk_user_id,
        ai_tool=ai_tool,
        provider=provider,
        model=model,
        body=body,
        prompt_summary=st.prompt_summary,
        user_email=_user_email,
        agent_identity_id=str(_agent_identity_id) if _agent_identity_id else None,
        route=st.request.url.path,
        hook_session_id=st.hook_session_id,
        routing_meta=_routing_meta,
        conductai_run_id=st.run_id,
        conductai_workflow=st.workflow,
        conductai_workflow_id=st.workflow_id,
        request_correlation_id=None,  # already merged into _routing_meta above
        idempotency_key=st.client_request_id,  # #2403 item 1
    )
    if _durable.fail_response is not None:
        return _durable.fail_response
    st.durable = _durable
    _durable_row_id = st.durable_row_id = _durable.row_id
    # R5 fix (reviewer P1): the reservation row and the drawer query
    # correlate via the audit row's request_id (not its row_id).
    # The lifecycle mints request_id even when durable audit is off.
    # Keep the row-id fallback for older lifecycle integrations.
    _audit_request_id = _durable.request_id or _durable_row_id
    st.audit_request_id = _audit_request_id

    # ── PR-A2b: pre-flight budget reservation ─────────────────────
    # Reserve applicable hard-cap budgets before dispatch. The helper
    # itself checks ``BUDGET_LEDGER_ENABLED`` and returns DISABLED
    # when off, so zero behavior change until ops flips the flag on.
    # Fail-CLOSED: any non-ACCEPTED outcome closes the audit row and
    # returns a budget-block response (402/503, see helper).
    from app.modules.guard.gateway_lifecycle import (
        budget_block_response as _budget_block_response,
        estimate_budget_cents as _estimate_budget_cents,
        reserve_budgets_for_request as _reserve_budgets_for_request,
        ReserveOutcome as _ReserveOutcome,
    )
    try:
        from app.modules.guard.gateway_lifecycle import (
            estimate_budget_micros as _estimate_budget_micros,
        )
    except ImportError:  # backward compat if module hasn't been redeployed
        _estimate_budget_micros = None
    # R3 fix (reviewer P1): reserve owns its own session lifecycle
    # inside a threadpool call. No shared session held across the
    # upstream await, no sync SQL/Redis on the event loop.
    def _reserve_sync_owned():
        _db = SessionLocal()
        try:
            return _reserve_budgets_for_request(
                db=_db,
                workspace_id=workspace_id,
                agent_identity_id=(
                    str(_agent_identity_id) if _agent_identity_id else None
                ),
                transport="gateway",
                client_tool=(ai_tool if ai_tool and ai_tool != "gateway" else None),
                clerk_user_id=clerk_user_id,
                estimated_cents=_estimate_budget_cents(body, provider, model, ai_tool),
                # R9 (reviewer P1): microdollar precision so the ledger's
                # Redis counter accumulates sub-cent requests correctly
                # instead of rounding to zero.
                estimated_micros=(
                    _estimate_budget_micros(body, provider, model, ai_tool)
                    if _estimate_budget_micros is not None
                    else None
                ),
                request_id=_audit_request_id,
            )
        finally:
            try:
                _db.close()
            except Exception:
                pass
    try:
        _reserve_result = await run_in_threadpool(_reserve_sync_owned)
    except Exception as _reserve_exc:  # noqa: BLE001
        log.warning("guard.gateway.reserve_wire_raised", err=str(_reserve_exc))
        # R7 fix (reviewer P1): the exception path used to leave
        # ``_reserve_result = None`` and fall through to dispatch —
        # a fail-OPEN branch that bypassed hard-cap enforcement
        # whenever the helper raised (bad SessionLocal, transient
        # DB blip, estimator error). Represent unexpected failures
        # as a synthetic DB_ERROR so the same rejection path fires
        # UNLESS the ledger is entirely disabled (flag off preserves
        # pre-PR-A behavior — no enforcement, no synthetic reject).
        from app.core.budget_ledger import enabled as _ledger_enabled
        if _ledger_enabled():
            from app.modules.guard.gateway_lifecycle import (
                ReserveBudgetsResult as _RBR,
            )
            _reserve_result = _RBR(
                outcome=_ReserveOutcome.DB_ERROR,
                error=f"reserve raised: {type(_reserve_exc).__name__}",
            )
        else:
            _reserve_result = None
    # Reserve failed = fail-closed reject (any non-ACCEPTED outcome).
    if _reserve_result is not None and _reserve_result.outcome in (
        _ReserveOutcome.EXCEEDED,
        _ReserveOutcome.NOT_READY,
        _ReserveOutcome.REDIS_DOWN,
        _ReserveOutcome.DB_ERROR,
    ):
        # R6 fix (reviewer P1): finalize the audit row as blocked
        # BEFORE cancelling the renewal task. Previously the row
        # stayed in 'accepted' state until lease expiry; the
        # reconciler then reported 'orphaned' instead of the real
        # refusal outcome. Rule_id encodes the specific refusal
        # so Flight Recorder + drawer can label it correctly.
        _refusal_rule = {
            _ReserveOutcome.EXCEEDED:   "guard.budget_cap_exceeded",
            _ReserveOutcome.NOT_READY:  "guard.budget_ledger_not_ready",
            _ReserveOutcome.REDIS_DOWN: "guard.budget_ledger_unavailable",
            _ReserveOutcome.DB_ERROR:   "guard.budget_ledger_error",
        }[_reserve_result.outcome]
        if _durable_row_id:
            try:
                await _finalize_durable_row(
                    row_id=_durable_row_id,
                    workspace_id=workspace_id,
                    decision="blocked",
                    provider=provider,
                    model=model,
                    body=body,
                    response_bytes=None,
                    duration_ms=int((time.monotonic() - st.started) * 1000),
                    rule_id=_refusal_rule,
                    routing_meta=_routing_meta,
                    execution_status="error",
                    result_summary=_reserve_result.error,
                    clerk_user_id=clerk_user_id,
                    ai_tool=ai_tool,
                    user_email=_user_email,
                )
            except Exception:
                log.exception(
                    "guard.gateway.refusal_finalize_failed",
                    row_id=_durable_row_id,
                    outcome=_reserve_result.outcome.value,
                )
        await _close_durable(_durable)
        return _budget_block_response(_reserve_result)
    if _reserve_result is not None:
        st.reservations = _reserve_result.reservations or []
    return None
