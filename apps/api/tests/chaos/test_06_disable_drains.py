"""Chaos 6 — flag flip mid-flight drains cleanly.

Scenario: a reservation is open (mid-request). Ops flips
``BUDGET_LEDGER_ENABLED=false``. New requests correctly go DISABLED,
but the already-open reservation must still be able to settle so its
Redis capacity gets released.
"""
from __future__ import annotations

import uuid

import pytest


def test_open_reservation_can_still_settle_after_flag_flip_off(
    warm_ledger,
    chaos_redis,
    chaos_db,
    unique_workspace_id,
    monkeypatch,
):
    """Reserve while flag is on. Flip off. Commit the reservation —
    the primitive commit() must still work because the flag gates the
    entry point (reserve_budgets_for_request), not the underlying
    ledger operations."""
    from app.core.budget_ledger import BudgetDecision, enabled_for

    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "true")
    monkeypatch.delenv("BUDGET_LEDGER_ALLOWLIST", raising=False)

    d, res = warm_ledger.reserve(
        db=chaos_db,
        workspace_id=unique_workspace_id,
        ai_tool=None,
        estimated_micros=8_000,
        cap_micros=10_000,
    )
    assert d == BudgetDecision.ACCEPTED
    chaos_db.commit()

    # Flag off mid-flight.
    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "false")
    assert enabled_for(unique_workspace_id) is False

    # Existing reservation must still be settleable via commit().
    warm_ledger.commit(
        db=chaos_db,
        reservation=res,
        actual_micros=8_000,
    )
    chaos_db.commit()

    # Redis reserved counter drops to 0, committed goes to 8_000.
    assert warm_ledger.current_reserved_micros(unique_workspace_id, None) == 0
    assert warm_ledger.current_committed_micros(unique_workspace_id, None) == 8_000

    # Durable row status flipped.
    from app.modules.guard.models import BudgetReservation

    row = chaos_db.query(BudgetReservation).filter(
        BudgetReservation.id == uuid.UUID(res.reservation_id),
    ).first()
    assert row.status == "committed"


def test_release_still_works_after_flag_flip_off(
    warm_ledger,
    chaos_redis,
    chaos_db,
    unique_workspace_id,
    monkeypatch,
):
    """Same story for release() — an in-flight cancel must still return
    the held capacity even after ops flipped the flag."""
    from app.core.budget_ledger import BudgetDecision

    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "true")
    monkeypatch.delenv("BUDGET_LEDGER_ALLOWLIST", raising=False)

    d, res = warm_ledger.reserve(
        db=chaos_db,
        workspace_id=unique_workspace_id,
        ai_tool=None,
        estimated_micros=3_000,
        cap_micros=10_000,
    )
    assert d == BudgetDecision.ACCEPTED
    chaos_db.commit()

    # Flag off.
    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "false")

    warm_ledger.release(db=chaos_db, reservation=res)
    chaos_db.commit()

    # Capacity fully refunded.
    assert warm_ledger.current_reserved_micros(unique_workspace_id, None) == 0
