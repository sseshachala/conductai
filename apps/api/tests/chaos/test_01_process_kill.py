"""Chaos 1 — process kill mid-reserve.

Scenario: worker A calls reserve() and the durable row lands in Postgres +
Redis counter increments. Then the worker crashes (kill -9) before the
caller settled. Worker B starts fresh, runs the reconciler, and needs to
rebuild Redis so the counter matches the durable log.

Expected result:

- The 'open' reservation row survives in Postgres (durable log).
- Fresh worker's reconciler reads that row and re-inflates the Redis
  counter to include it.
- Subsequent reserves in the new worker respect the pre-crash hold.
"""
from __future__ import annotations

import uuid

import pytest


def test_open_reservation_survives_worker_restart_and_reconciler_rebuilds_redis(
    warm_ledger,
    chaos_redis,
    chaos_db,
    unique_workspace_id,
    monkeypatch,
):
    """Worker A reserves 500 micros. Simulate crash: forget Redis (flush)
    but keep Postgres. Worker B (fresh ledger instance + fresh Redis
    view) runs reconcile — Redis counter must come back to 500 so the
    caller's held capacity is honored.
    """
    from app.core.budget_ledger import BudgetDecision, BudgetLedger

    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "true")

    # Worker A: reserve 500 micros against a $10 cap.
    decision, res = warm_ledger.reserve(
        db=chaos_db,
        workspace_id=unique_workspace_id,
        ai_tool=None,
        estimated_micros=500,
        cap_micros=10 * 1_000_000,
    )
    assert decision == BudgetDecision.ACCEPTED
    chaos_db.commit()

    # Sanity — Redis actually holds 500.
    assert warm_ledger.current_reserved_micros(unique_workspace_id, None) == 500

    # Simulate the crash: wipe Redis so the next process starts cold.
    chaos_redis.flushall()

    # Worker B — new BudgetLedger instance pointed at the same Redis.
    worker_b = BudgetLedger(redis_client=chaos_redis)
    worker_b.reconcile(
        db=chaos_db,
        workspace_id=unique_workspace_id,
        ai_tool=None,
    )

    # Reconciler must have re-inflated Redis to include the surviving
    # open reservation. The 500 micros hold is honored.
    assert worker_b.current_reserved_micros(unique_workspace_id, None) == 500

    # Worker B accepts a new reserve within remaining capacity.
    decision2, res2 = worker_b.reserve(
        db=chaos_db,
        workspace_id=unique_workspace_id,
        ai_tool=None,
        estimated_micros=200,
        cap_micros=10 * 1_000_000,
    )
    assert decision2 == BudgetDecision.ACCEPTED
    chaos_db.commit()

    # Total reserved after new hold = 700 micros.
    assert worker_b.current_reserved_micros(unique_workspace_id, None) == 700
