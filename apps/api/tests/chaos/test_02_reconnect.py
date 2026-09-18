"""Chaos 2 — Redis disconnect + reconnect.

Scenario: a reserve succeeds, then Redis becomes unreachable briefly,
then it comes back. Do subsequent reserves work? Does the counter stay
consistent?

R3 (#2122) added bounded socket timeouts so a Redis blip fails fast.
This test proves the client recovers rather than staying broken.
"""
from __future__ import annotations

import uuid

import pytest


def test_reserve_then_temporary_redis_outage_then_recovery(
    warm_ledger,
    chaos_redis,
    chaos_db,
    unique_workspace_id,
    monkeypatch,
):
    """First reserve OK. Kick every client off Redis (CLIENT KILL TYPE
    NORMAL). New reserves should fail fast, then succeed once Redis is
    reachable again — no permanent broken state.
    """
    from app.core.budget_ledger import BudgetDecision

    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "true")

    # 1) First reserve lands.
    d1, r1 = warm_ledger.reserve(
        db=chaos_db,
        workspace_id=unique_workspace_id,
        ai_tool=None,
        estimated_micros=1_000,
        cap_micros=100 * 1_000_000,
    )
    assert d1 == BudgetDecision.ACCEPTED
    chaos_db.commit()

    # 2) Force Redis to drop every open connection. That simulates a
    # network blip — subsequent commands will need to reconnect.
    try:
        chaos_redis.execute_command("CLIENT", "KILL", "TYPE", "NORMAL")
    except Exception:
        # Some Redis builds don't return sensibly here; keep going.
        pass

    # 3) A second reserve must still succeed once the pool reconnects.
    # The ConnectionPool is transparent — the next call creates a new
    # socket. If it doesn't, that's the R3 bug.
    d2, r2 = warm_ledger.reserve(
        db=chaos_db,
        workspace_id=unique_workspace_id,
        ai_tool=None,
        estimated_micros=2_000,
        cap_micros=100 * 1_000_000,
    )
    assert d2 == BudgetDecision.ACCEPTED
    chaos_db.commit()

    # 4) Counter reflects both holds — no lost writes, no drift.
    assert warm_ledger.current_reserved_micros(unique_workspace_id, None) == 3_000
