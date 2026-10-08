"""Gateway lifecycle — budget reservation: reserve/settle helpers, request-cost estimation and the block response."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import structlog
from enum import Enum as _EnumRS

log = structlog.get_logger("app.modules.guard.gateway_lifecycle")


# ─── PR-A2a: budget reservation helpers (dark, unwired) ─────────────
#
# Two helpers that own the reserve/settle contract from the corrected
# design review:
#
#   choose -> policy -> RESERVE -> execute one attempt -> outcome -> SETTLE
#
# They are called from the gateway request path in PR-A2b, gated behind a
# feature flag. This PR ships the helpers dark so their semantics can be
# reviewed and tested in isolation before any behavior change ships.
#
# Correctness rules baked in per the design review:
#
#   1. Fail-CLOSED on any ambiguity for HARD caps. NOT_READY, REDIS_DOWN,
#      DB failure -> reject the request. Fail-open is never valid for hard
#      budget enforcement. Soft budgets alert only; they are excluded from
#      reserve_all() and cannot block dispatch.
#   2. Release only when dispatch DEFINITELY did not happen. After bytes
#      leave the socket, the provider may charge us even if we disconnect;
#      release then would refund a real spend. Post-dispatch failures are
#      marked settle-pending; the reconciler catches them via lease expiry.
#   3. Estimated cents = input + bounded output allowance + fallback headroom.
#      The gateway handler computes that number and passes it in; this helper
#      does not estimate. Integer cents; sub-cent (millicents) is a later
#      schema change if needed.
#
# The helpers stay pure: no upstream IO, no policy eval, no audit writes.


class ReserveOutcome(_EnumRS):
    """What happened when we tried to reserve budgets for a request."""
    ACCEPTED_NO_HARD_CAP = "accepted_no_hard_cap"
    ACCEPTED_WITH_RESERVATIONS = "accepted_with_reservations"
    EXCEEDED = "exceeded"
    NOT_READY = "not_ready"
    REDIS_DOWN = "redis_down"
    DB_ERROR = "db_error"
    DISABLED = "disabled"


@dataclass
class ReserveBudgetsResult:
    """Structured return so the caller can branch on outcome without
    inspecting the ledger's internal decision enum."""
    outcome: ReserveOutcome
    reservations: list = None  # list[Reservation] when ACCEPTED_*, else None
    refusing_budget: object = None  # the GuardSpendBudget that refused
    error: str = None  # human-readable for the block reason chip


def reserve_budgets_for_request(
    db: Any,
    *,
    workspace_id: str,
    agent_identity_id: str | None,
    transport: str | None,
    client_tool: str | None,
    clerk_user_id: str | None,
    estimated_cents: int,
    request_id: str,
    estimated_micros: int | None = None,
) -> ReserveBudgetsResult:
    """Reserve all applicable hard-cap budgets for a request.

    Flow:
      1. lookup_applicable_budgets(scope) -> list of budget rows.
      2. reserve_all(rows, estimated_cents) -> (decision, reservations, refusing).
      3. Translate ledger decision to a ReserveOutcome the gateway handler
         can pattern-match on.

    Fail-CLOSED contract: NOT_READY / REDIS_DOWN / DB error on a request
    that HAS hard-capped budgets -> the caller MUST reject the request.
    Never allow paid dispatch when the enforcement layer cannot confirm
    capacity. (For soft-only budgets the outcome is ACCEPTED_NO_HARD_CAP
    because reserve_all() short-circuits to an empty list.)

    The ledger's own kill switch (BUDGET_LEDGER_ENABLED) is respected —
    when off, this helper returns DISABLED and the caller should behave
    as it did pre-PR-A (post-hoc spend tracking, no pre-flight blocking).
    """
    from app.core.budget_ledger import (
        BudgetDecision,
        enabled_for as _ledger_enabled_for,
        get_budget_ledger,
    )
    from app.modules.guard.spend_lookup import lookup_applicable_budgets

    if not _ledger_enabled_for(workspace_id):
        return ReserveBudgetsResult(outcome=ReserveOutcome.DISABLED)
    # Emit the enforcement-active metric so ops can see who is on the
    # ledger during the canary. Cardinality is bounded by the allowlist.
    try:
        from app.modules.guard.observability.metrics import (
            GUARD_BUDGET_ENFORCEMENT_ACTIVE,
        )
        GUARD_BUDGET_ENFORCEMENT_ACTIVE.labels(workspace_id=str(workspace_id)).inc()
    except Exception:  # noqa: BLE001 — never let observability break enforcement
        pass

    import uuid as _uuid
    try:
        ws_uuid = _uuid.UUID(workspace_id)
    except (ValueError, TypeError):
        # Malformed workspace id — reject, do not fail-open.
        return ReserveBudgetsResult(
            outcome=ReserveOutcome.DB_ERROR,
            error="invalid workspace_id",
        )

    try:
        applicable = lookup_applicable_budgets(
            db,
            ws_uuid,
            agent_identity_id=agent_identity_id,
            transport=transport,
            client_tool=client_tool,
            clerk_user_id=clerk_user_id,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("guard.gateway.applicable_budgets_lookup_failed", err=str(e))
        return ReserveBudgetsResult(
            outcome=ReserveOutcome.DB_ERROR,
            error="budget lookup failed",
        )

    ledger = get_budget_ledger()

    try:
        decision, reservations, refusing = ledger.reserve_all(
            db=db,
            workspace_id=workspace_id,
            applicable_budgets=applicable,
            estimated_cents=estimated_cents,
            estimated_micros=estimated_micros,
            agent_identity_id=agent_identity_id,
            source=transport,
            client_tool=client_tool,
            request_id=request_id,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("guard.gateway.reserve_all_raised", err=str(e))
        return ReserveBudgetsResult(
            outcome=ReserveOutcome.DB_ERROR,
            error="reserve_all raised",
        )

    if decision == BudgetDecision.ACCEPTED:
        if not reservations:
            return ReserveBudgetsResult(
                outcome=ReserveOutcome.ACCEPTED_NO_HARD_CAP,
                reservations=[],
            )
        return ReserveBudgetsResult(
            outcome=ReserveOutcome.ACCEPTED_WITH_RESERVATIONS,
            reservations=reservations,
        )
    if decision == BudgetDecision.EXCEEDED:
        return ReserveBudgetsResult(
            outcome=ReserveOutcome.EXCEEDED,
            refusing_budget=refusing,
            error="budget cap exceeded",
        )
    if decision == BudgetDecision.NOT_READY:
        return ReserveBudgetsResult(
            outcome=ReserveOutcome.NOT_READY,
            error="budget ledger not ready (reconciler cold start)",
        )
    if decision == BudgetDecision.REDIS_DOWN:
        return ReserveBudgetsResult(
            outcome=ReserveOutcome.REDIS_DOWN,
            error="budget ledger unavailable",
        )
    # DISABLED (shouldn't reach here — filtered above) and any unknown
    # decision -> conservative: DB_ERROR so the caller rejects.
    return ReserveBudgetsResult(
        outcome=ReserveOutcome.DB_ERROR,
        error=f"unexpected ledger decision: {decision!r}",
    )


class SettleAction(_EnumRS):
    """What settlement did with the reservations."""
    COMMITTED = "committed"           # success path: actual_cents committed to every budget
    RELEASED = "released"             # pre-dispatch error: reservations refunded
    PENDING_RECONCILER = "pending"    # post-dispatch failure: reconciler owns cleanup
    NOOP = "noop"                     # empty reservation list: nothing to do
    DISABLED = "disabled"             # ledger flag off; caller passed no reservations


@dataclass
class SettleResult:
    action: SettleAction
    reservations_processed: int = 0


def settle_reservations(
    db: Any,
    reservations: list,
    *,
    dispatched: bool,
    actual_cents: int | None,
    actual_micros: int | None = None,
) -> SettleResult:
    """Post-outcome settlement of reserved budgets.

    Truth table:

    +------------+---------------+----------------+---------------------+
    | dispatched | actual_cents  | Action         | Why                 |
    +============+===============+================+=====================+
    | True       | int           | commit_all(N)  | Success — charge    |
    +------------+---------------+----------------+---------------------+
    | True       | None          | leave open     | Bytes flew, outcome |
    |            |               | (pending)      | unknown, reconciler |
    |            |               |                | catches via lease   |
    |            |               |                | expiry.             |
    +------------+---------------+----------------+---------------------+
    | False      | any           | release_all    | No wire bytes, safe |
    |            |               |                | to refund.          |
    +------------+---------------+----------------+---------------------+

    The dispatched-True + actual_cents-None case is the load-bearing
    correctness rule: NEVER release after dispatch, because the provider
    may have processed the request and will bill us — refunding then
    silently drops real spend.

    Empty reservations list is a no-op (ACCEPTED_NO_HARD_CAP path from
    reserve_budgets_for_request).
    """
    if not reservations:
        return SettleResult(action=SettleAction.NOOP, reservations_processed=0)

    from app.core.budget_ledger import get_budget_ledger
    ledger = get_budget_ledger()

    if not dispatched:
        # Definitely no wire bytes — safe to refund every reservation.
        ledger.release_all(db=db, reservations=reservations)
        return SettleResult(
            action=SettleAction.RELEASED,
            reservations_processed=len(reservations),
        )

    if actual_cents is None:
        # Bytes flew but we don't have a confirmed outcome. DO NOT release —
        # the provider may have processed the request. Leave the reservations
        # open; the reconciler catches them via lease expiry and finalizes
        # via the durable audit row's outcome (finalized / orphaned / expired).
        log.warning(
            "guard.gateway.settle_pending_reconciler",
            reservation_ids=[r.reservation_id for r in reservations],
        )
        return SettleResult(
            action=SettleAction.PENDING_RECONCILER,
            reservations_processed=len(reservations),
        )

    # Success path — commit the actual cost to every budget the request
    # drew from. Each budget receives the FULL actual_cents (see docstring
    # on ledger.commit_all).
    ledger.commit_all(
        db=db,
        reservations=reservations,
        actual_cents=int(actual_cents) if actual_cents is not None else 0,
        actual_micros=int(actual_micros) if actual_micros is not None else None,
    )
    return SettleResult(
        action=SettleAction.COMMITTED,
        reservations_processed=len(reservations),
    )


# ─── PR-A2b: request-cost estimation + block response ──────────────
#
# Two small helpers the gateway wire-in needs. Kept alongside the
# reserve/settle helpers so the whole budget-reservation surface reads
# in one file.
#
# ``estimate_budget_cents()`` is a bounded heuristic — input tokens
# (approximate from prompt length) plus a bounded output allowance
# (max_tokens from the request, else a safe default). Multiplied by the
# tool's known per-1M-token pricing. Integer cents; sub-cent rounding is
# a follow-up if it matters.
#
# ``budget_block_response()`` maps a fail-closed reserve outcome to an
# HTTP response that carries the block reason for the drawer + block
# chip UI in the follow-up.

# #2209 Tier 1: was a compat shim over ``runtime.accounting.estimator`` and
# ``.pricing``. Rewired to call the accounting engine directly — the
# messages-only char-sum heuristic is retained as the ``TokensEstimate``
# includes it via ``InputShape.MESSAGES`` when full coverage matters.


def estimate_budget_micros(
    body: dict,
    provider: str,
    model: str,
    ai_tool: str | None,
) -> int:
    """Microdollar-precision pre-flight cost estimate for the ledger reservation.

    Reads directly from the shared accounting engine — same estimator +
    PricingService the receipts use. Ceiling-rounded because
    over-reservation is safer than under-reservation (settlement writes
    the real cost via ``commit_all``).
    """
    import math as _math
    from decimal import Decimal

    from app.runtime.accounting.estimator import estimate_tokens
    from app.runtime.accounting.pricing import default_pricing_service

    est = estimate_tokens(body)
    input_tokens = est.input_tokens
    output_tokens = est.output_tokens_allowance

    usd: float | None = None
    try:
        card = default_pricing_service().get_rate_card(provider, model, strict=False)
        usd = float(
            (
                Decimal(input_tokens) * card.input_per_1m_usd
                + Decimal(output_tokens) * card.output_per_1m_usd
            )
            / Decimal(1_000_000)
            + card.request_fee_usd
        )
    except Exception:
        usd = None
    if usd is None:
        # Unknown model or rate-card lookup failure. Fall back to a
        # conservative per-tool default so the reservation still gates
        # runaway spend under lookup failure. Same guard.audit intent
        # as before the shim retirement.
        try:
            from app.modules.guard.routers.events import _tool_pricing

            tool_key = (ai_tool or "unknown").lower()
            pricing = _tool_pricing(tool_key)
        except Exception:
            pricing = {"input": 3.0, "output": 15.0}
        input_usd = (input_tokens * float(pricing.get("input", 3.0))) / 1_000_000
        output_usd = (output_tokens * float(pricing.get("output", 15.0))) / 1_000_000
        usd = input_usd + output_usd

    return _math.ceil(usd * 1_000_000)


def estimate_budget_cents(
    body: dict,
    provider: str,
    model: str,
    ai_tool: str | None,
) -> int:
    """Cents-precision estimate. Thin wrapper around ``estimate_budget_micros``."""
    import math as _math

    return _math.ceil(estimate_budget_micros(body, provider, model, ai_tool) / 10_000)


def budget_block_response(result):
    """Build a fail-closed HTTP response for a rejected reservation.

    Maps every non-ACCEPTED outcome to an appropriate status + reason:

      EXCEEDED    -> 402 (payment required), refusing budget in body
      NOT_READY   -> 503 (service unavailable, ledger cold-start)
      REDIS_DOWN  -> 503 (ledger unavailable)
      DB_ERROR    -> 503 (generic ledger error)

    Response body carries a ``reason`` chip the drawer UI (PR-B) can
    render. Cardinality-safe — never includes workspace_id or agent_id
    in the reason text.
    """
    from fastapi.responses import JSONResponse
    outcome_str = getattr(result.outcome, "value", str(result.outcome))
    if outcome_str == ReserveOutcome.EXCEEDED.value:
        status = 402
    else:
        status = 503
    refusing = None
    if result.refusing_budget is not None:
        refusing = {
            "ai_tool": getattr(result.refusing_budget, "ai_tool", None),
            "hard_limit_usd": getattr(result.refusing_budget, "hard_limit_usd", None),
        }
    return JSONResponse(
        status_code=status,
        content={
            "type": "budget_reservation_refused",
            "outcome": outcome_str,
            "reason": result.error or "budget reservation refused",
            "refusing_budget": refusing,
        },
    )
