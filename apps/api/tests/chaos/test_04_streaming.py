"""Chaos 4 — streaming request that gets cut off mid-stream.

Scenario: caller reserves 5000 micros for an expected 30-second stream.
Stream delivers 60% of its usage then the client disconnects. The
handler treats this as ``dispatched=True + actual_cents=None`` — settle
must NOT release (bytes flew, provider may bill us) and NOT commit (we
don't know the real cost). Reconciler resolves later.
"""
from __future__ import annotations

import uuid

import pytest


def test_streaming_cancel_marks_pending_reconciler_not_release_not_commit(
    warm_ledger,
    chaos_redis,
    chaos_db,
    unique_workspace_id,
    monkeypatch,
):
    """Reserve → the stream disconnects → settle helper decides. Since
    dispatch happened but cost is unknown, the reservation stays open
    with capacity held. Reconciler will resolve it once the audit row
    lifecycle finalizes.
    """
    from app.core.budget_ledger import BudgetDecision
    from app.modules.guard.gateway_lifecycle import (
        SettleAction,
        settle_reservations,
    )

    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "true")

    decision, res = warm_ledger.reserve(
        db=chaos_db,
        workspace_id=unique_workspace_id,
        ai_tool=None,
        estimated_micros=5_000,
        cap_micros=10 * 1_000_000,
    )
    assert decision == BudgetDecision.ACCEPTED
    chaos_db.commit()

    # Client dropped mid-stream: dispatched=True (bytes flew) but we
    # never saw the final usage frame → actual_cents is None.
    result = settle_reservations(
        db=chaos_db,
        reservations=[res],
        dispatched=True,
        actual_cents=None,
        actual_micros=None,
    )
    assert result.action == SettleAction.PENDING_RECONCILER

    # Redis still holds the 5000 micros — nobody released or committed.
    assert warm_ledger.current_reserved_micros(unique_workspace_id, None) == 5_000
    assert warm_ledger.current_committed_micros(unique_workspace_id, None) == 0

    # Durable row still ``open`` — reconciler will pick it up on the
    # next sweep once the audit lifecycle_state flips to finalized or
    # orphaned.
    from app.modules.guard.models import BudgetReservation

    row = chaos_db.query(BudgetReservation).filter(
        BudgetReservation.id == uuid.UUID(res.reservation_id),
    ).first()
    assert row is not None
    assert row.status == "open"
