"""Chaos 5 — month rollover.

Scenario: it's the last minute of the month. A reserve lands. Then the
clock ticks past midnight. A second reserve lands. The two must go to
DIFFERENT period keys — never share a Redis counter or cross-charge
each other's caps.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest


def test_reservations_on_either_side_of_month_boundary_use_different_counters(
    chaos_ledger,
    chaos_redis,
    chaos_db,
    unique_workspace_id,
    monkeypatch,
):
    """Fake ``monthly_period_key`` so the second reserve sees the next
    month. The two reservations must not share Redis state and must not
    share caps.
    """
    from app.core.budget_ledger import BudgetDecision
    from app.core import budget_ledger as bl

    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "true")

    # 1) Pre-rollover reserve — period = 2026-01.
    monkeypatch.setattr(bl, "monthly_period_key", lambda now=None: "2026-01")
    # Reconcile the Jan scope so it's `ready` before reserve.
    chaos_ledger.reconcile(db=chaos_db, workspace_id=unique_workspace_id, ai_tool=None)
    d1, r1 = chaos_ledger.reserve(
        db=chaos_db,
        workspace_id=unique_workspace_id,
        ai_tool=None,
        estimated_micros=6_000,
        cap_micros=10_000,  # tight cap so any crossover would refuse
    )
    assert d1 == BudgetDecision.ACCEPTED
    chaos_db.commit()

    # 2) Rollover — period = 2026-02.
    monkeypatch.setattr(bl, "monthly_period_key", lambda now=None: "2026-02")
    # Reconcile Feb scope too so it's `ready` before the second reserve.
    chaos_ledger.reconcile(db=chaos_db, workspace_id=unique_workspace_id, ai_tool=None)

    # New period must start with a fresh counter — a 6_000 reserve
    # against the same 10_000 cap fits again because the January hold
    # is not counted here.
    d2, r2 = chaos_ledger.reserve(
        db=chaos_db,
        workspace_id=unique_workspace_id,
        ai_tool=None,
        estimated_micros=6_000,
        cap_micros=10_000,
    )
    assert d2 == BudgetDecision.ACCEPTED, (
        "second reserve after rollover was refused — the two periods "
        "are sharing a counter, which is the rollover bug."
    )
    chaos_db.commit()

    # 3) The two reservations live under DIFFERENT scope keys with the
    # same workspace but different period. Confirm the Redis reserved
    # totals do not mix.
    monkeypatch.setattr(bl, "monthly_period_key", lambda now=None: "2026-01")
    jan_reserved = chaos_ledger.current_reserved_micros(unique_workspace_id, None)
    monkeypatch.setattr(bl, "monthly_period_key", lambda now=None: "2026-02")
    feb_reserved = chaos_ledger.current_reserved_micros(unique_workspace_id, None)
    assert jan_reserved == 6_000
    assert feb_reserved == 6_000
