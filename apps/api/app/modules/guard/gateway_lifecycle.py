"""Durable-audit lifecycle for the Gateway surface.

Owns the full two-phase durable-audit lifecycle so the legacy
``routers/proxy.py`` file never grows Gateway behavior:

    open_durable_row()     insert_accepted + start whole-request renewal
    close_durable_row()    cancel renewal task (idempotent)
    finalize_durable_row() supervised finalize (bounded shield + strong ref)

Callers see a small dataclass with either a ``fail_response`` to return
immediately (durable write failed and the operator is configured
fail-closed) or a ``row_id`` + ``renewal_task`` pair to thread through
the request lifetime.

Hard-kill loss is caught by the Phase 4 reconciler; the supervised
task pattern here reduces the loss window to "process killed within a
few hundred ms of stream end."
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any

import structlog

from app.core.config import settings
from app.guard.audit import finalize, insert_accepted, renew_lease
from app.guard.router import fail_closed as _fail_closed


log = structlog.get_logger(__name__)


# Module-level strong-ref set so an in-flight finalize task cannot be
# GC'd by the loop before it completes. One set per worker process.
_PENDING_FINALIZES: set[asyncio.Task] = set()


@dataclass
class DurableRow:
    """Handle threaded through the request lifecycle.

    Exactly one of ``row_id`` or ``fail_response`` will be set — never
    both, never neither when the caller enters the durable path.
    """
    row_id: str | None = None
    renewal_task: asyncio.Task | None = None
    fail_response: Any = None


# ─── Open ─────────────────────────────────────────────────────────────


async def open_durable_row(
    *,
    workspace_id: str,
    clerk_user_id: str | None,
    ai_tool: str,
    provider: str,
    model: str,
    body: dict,
    prompt_summary: str,
    user_email: str | None,
    agent_identity_id: str | None,
    route: str,
    hook_session_id: str | None,
    routing_meta: dict | None,
    conductai_run_id: str | None,
    conductai_workflow: str | None,
    conductai_workflow_id: str | None,
    request_correlation_id: str | None,
) -> DurableRow:
    """Insert the accepted row and start whole-request lease renewal.

    Returns a ``DurableRow`` with ``row_id`` + optional ``renewal_task``
    on success, or ``fail_response`` set on real write failure (503) /
    UUID4 collision (409).
    """
    from sqlalchemy.exc import IntegrityError

    # #1995 canary — deterministic per-workspace gate. Global flag is
    # still the kill switch; allowlist + pct control incremental rollout
    # without a code deploy. Same workspace always lands in the same
    # bucket, so a workspace never oscillates between the two writer
    # paths mid-session.
    if not settings.durable_audit_enabled_for(workspace_id):
        return DurableRow()

    # Server-owned request_id. Client X-Request-Id lives in routing_meta.
    # client_request_id as correlation metadata only — never a
    # uniqueness key because a client-supplied value cannot be trusted
    # for cross-tenant safety.
    request_id = str(uuid.uuid4())
    if request_correlation_id and isinstance(routing_meta, dict):
        routing_meta = {**routing_meta, "client_request_id": request_correlation_id}
    elif request_correlation_id:
        routing_meta = {"client_request_id": request_correlation_id}

    try:
        row_id = insert_accepted(
            workspace_id, clerk_user_id, ai_tool, provider, model,
            request_id=request_id,
            body=body,
            prompt_summary=prompt_summary,
            user_email=user_email,
            agent_identity_id=agent_identity_id,
            route=route,
            hook_session_id=hook_session_id,
            routing_meta=routing_meta,
            conductai_run_id=conductai_run_id,
            conductai_workflow=conductai_workflow,
            conductai_workflow_id=conductai_workflow_id,
        )
    except IntegrityError:
        # Server-generated UUID4 collision is astronomically unlikely
        # (2^-122). Return generic 409 with no receipt or state.
        log.warning(
            "guard.gateway.internal_request_id_collision",
            request_id=request_id,
        )
        return DurableRow(fail_response=_fail_closed(
            409,
            "Duplicate durable-audit request id. Retry the request.",
        ))
    except Exception as e:
        if settings.guard_durable_audit_fail_closed:
            log.error(
                "guard.gateway.durable_audit_fail_closed",
                err=str(e),
                request_id=request_id,
            )
            return DurableRow(fail_response=_fail_closed(
                503,
                "Guard durable audit write failed — refusing to forward "
                "inference without a durable record. Retry the request.",
            ))
        log.warning(
            "guard.gateway.durable_audit_fail_open",
            err=str(e),
            request_id=request_id,
        )
        return DurableRow()

    # Whole-request renewal: covers the header-wait window on non-
    # streaming plus the initial-connect window on streaming.
    renew_interval = settings.guard_durable_audit_stream_renew_seconds
    renewal_task: asyncio.Task | None = None
    if renew_interval > 0:
        lease_seconds = settings.guard_durable_audit_lease_seconds
        renewal_task = asyncio.create_task(
            _renewal_loop(row_id, workspace_id, renew_interval, lease_seconds)
        )

    return DurableRow(row_id=row_id, renewal_task=renewal_task)


# ─── Close ────────────────────────────────────────────────────────────


async def close_durable_row(durable: DurableRow) -> None:
    """Cancel the whole-request renewal task. Idempotent."""
    if durable.renewal_task is None or durable.renewal_task.done():
        return
    durable.renewal_task.cancel()
    try:
        await durable.renewal_task
    except BaseException:
        pass


# ─── Finalize ─────────────────────────────────────────────────────────


async def finalize_durable_row(
    *,
    row_id: str,
    workspace_id: str,
    decision: str,
    provider: str,
    model: str,
    body: dict,
    response_bytes: bytes | None,
    duration_ms: int,
    rule_id: str | None,
    routing_meta: dict | None,
    execution_status: str | None,
    result_summary: str | None,
    clerk_user_id: str | None,
    ai_tool: str,
    user_email: str | None,
    bounded_timeout: float = 5.0,
) -> None:
    """Supervised finalize with bounded shield.

    Runs the sync ``finalize()`` SQL in a thread so the event loop is
    not blocked, wraps it in a shielded task with a strong module-level
    reference so it survives caller cancellation, and waits up to
    ``bounded_timeout`` for completion. On timeout the task keeps
    running under supervision; on caller cancellation the task keeps
    running and the caller sees the cancel.

    Phase 4 reconciler catches any tail that a hard-kill drops.
    """
    task = asyncio.create_task(
        asyncio.to_thread(
            finalize,
            row_id, workspace_id,
            decision=decision,
            provider=provider,
            model=model,
            body=body,
            response_bytes=response_bytes,
            duration_ms=duration_ms,
            rule_id=rule_id,
            routing_meta=routing_meta,
            execution_status=execution_status,
            result_summary=result_summary,
            clerk_user_id=clerk_user_id,
            ai_tool=ai_tool,
            user_email=user_email,
        )
    )
    _register_finalize_task(task, label=f"finalize:{row_id}")

    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=bounded_timeout)
    except asyncio.TimeoutError:
        log.info(
            "guard.gateway.finalize_bounded_wait_timeout",
            row_id=row_id,
            timeout=bounded_timeout,
        )
    except asyncio.CancelledError:
        log.info(
            "guard.gateway.finalize_bounded_wait_cancelled",
            row_id=row_id,
        )
        raise


def _register_finalize_task(task: asyncio.Task, *, label: str) -> None:
    _PENDING_FINALIZES.add(task)
    def _observe(t: asyncio.Task) -> None:
        _PENDING_FINALIZES.discard(t)
        if t.cancelled():
            log.warning("guard.gateway.finalize_cancelled", label=label)
            return
        exc = t.exception()
        if exc is not None:
            log.error("guard.gateway.finalize_failed", label=label, err=str(exc))
    task.add_done_callback(_observe)


# ─── Test hooks ───────────────────────────────────────────────────────


def pending_finalize_count() -> int:
    return len(_PENDING_FINALIZES)


async def drain_pending_finalizes(timeout: float = 5.0) -> int:
    if not _PENDING_FINALIZES:
        return 0
    pending = list(_PENDING_FINALIZES)
    done, still = await asyncio.wait(pending, timeout=timeout)
    return len(still)


# ─── Private helpers ──────────────────────────────────────────────────


async def _renewal_loop(
    row_id: str,
    workspace_id: str,
    renew_interval: int,
    lease_seconds: int,
) -> None:
    while True:
        try:
            await asyncio.sleep(renew_interval)
        except asyncio.CancelledError:
            return
        try:
            await asyncio.to_thread(
                renew_lease,
                row_id, workspace_id,
                additional_seconds=lease_seconds,
            )
        except Exception:
            log.warning("guard.gateway.whole_request_renewal_swallowed")


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


from enum import Enum as _EnumRS


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
        enabled as _ledger_enabled,
        get_budget_ledger,
    )
    from app.modules.guard.spend_lookup import lookup_applicable_budgets

    if not _ledger_enabled():
        return ReserveBudgetsResult(outcome=ReserveOutcome.DISABLED)

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
        actual_cents=int(actual_cents),
    )
    return SettleResult(
        action=SettleAction.COMMITTED,
        reservations_processed=len(reservations),
    )
