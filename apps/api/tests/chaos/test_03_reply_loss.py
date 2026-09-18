"""Chaos 3 — Redis applied the reservation, reply was lost.

Reviewer R8's ambiguous state. Redis's Lua script actually incremented
the counter, but the client's ``socket_timeout`` fired before the reply
came back. Pre-R8 the ledger deleted the durable row (leaking Redis
capacity). Post-R8 the row survives and the reconciler resolves it.

This test simulates the divergence by hand — apply the reserve script
directly against Redis (so the counter increments) and then verify that
a subsequent reserve on the same scope sees the pre-existing hold.
"""
from __future__ import annotations

import uuid

import pytest


def test_lost_reply_leaves_redis_ahead_reconciler_converges(
    chaos_ledger,
    chaos_redis,
    chaos_db,
    unique_workspace_id,
    monkeypatch,
):
    """Simulate the R8 scenario: Redis has 500 micros reserved but no
    corresponding durable row. Reconciler brings them back in sync by
    reading the durable log — the phantom Redis hold is cleared, so
    subsequent reserves have full capacity.
    """
    from app.core.budget_ledger import BudgetLedger, _scope_keys, monthly_period_key

    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "true")

    period = monthly_period_key()
    keys = _scope_keys(unique_workspace_id, None, None, None, period)

    # 1) Simulate: Redis incremented reserved to 500 but the caller never
    # persisted a durable row. Also seed the `ready` flag so the ledger
    # thinks reconcile has already run for this scope.
    chaos_redis.set(keys["reserved"], 500)
    chaos_redis.set(keys["ready"], "1")

    # 2) Reconciler reads the durable log (empty) and overwrites Redis so
    # phantom hold is cleared.
    chaos_ledger.reconcile(
        db=chaos_db,
        workspace_id=unique_workspace_id,
        ai_tool=None,
    )

    # Reserved counter should be zero — no durable row supports the 500.
    assert chaos_ledger.current_reserved_micros(unique_workspace_id, None) == 0

    # 3) A subsequent reserve sees full capacity again.
    from app.core.budget_ledger import BudgetDecision

    decision, res = chaos_ledger.reserve(
        db=chaos_db,
        workspace_id=unique_workspace_id,
        ai_tool=None,
        estimated_micros=250,
        cap_micros=1_000_000,
    )
    assert decision == BudgetDecision.ACCEPTED
    chaos_db.commit()

    assert chaos_ledger.current_reserved_micros(unique_workspace_id, None) == 250
