"""PR 6d — atomic budget-reservation ledger proofs.

Uses fakeredis to prove the Lua-scripted check-and-INCR is genuinely
atomic against concurrent reserves. Real Redis semantics apply: Lua
runs single-threaded on the server side, so any correct emulator
serialises the script body — fakeredis does.

Reviewer directive from prior PRs: prove the invariant (no reservation
overshoots the cap), prove the failure mode (release refunds cleanly,
Redis-down degrades safely), prove the kill switch is real.
"""
from __future__ import annotations

import threading

import fakeredis
import pytest


@pytest.fixture(autouse=True)
def _reset_singletons():
    from app.core.budget_ledger import reset_budget_ledger_for_tests
    reset_budget_ledger_for_tests()
    yield
    reset_budget_ledger_for_tests()


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def ledger(redis_client):
    from app.core.budget_ledger import BudgetLedger
    return BudgetLedger(redis_client=redis_client)


# ── Kill switch ─────────────────────────────────────────────────────

def test_kill_switch_default_off(monkeypatch):
    monkeypatch.delenv("BUDGET_LEDGER_ENABLED", raising=False)
    from app.core.budget_ledger import enabled
    assert enabled() is False


def test_kill_switch_on(monkeypatch):
    monkeypatch.setenv("BUDGET_LEDGER_ENABLED", "true")
    from app.core.budget_ledger import enabled
    assert enabled() is True


# ── Basic reserve/release ───────────────────────────────────────────

def test_reserve_within_cap_accepted(ledger):
    from app.core.budget_ledger import BudgetDecision
    decision, res = ledger.reserve(
        workspace_id="ws-1", ai_tool=None,
        estimated_cents=100, cap_cents=10_000, committed_cents=0,
    )
    assert decision == BudgetDecision.ACCEPTED
    assert res is not None
    assert res.estimated_cents == 100
    assert ledger.current_reserved_cents("ws-1", None) == 100


def test_reserve_over_cap_refused(ledger):
    from app.core.budget_ledger import BudgetDecision
    decision, res = ledger.reserve(
        workspace_id="ws-1", ai_tool=None,
        estimated_cents=200, cap_cents=100, committed_cents=0,
    )
    assert decision == BudgetDecision.EXCEEDED
    assert res is None
    # No side effect — reserved counter must not have moved.
    assert ledger.current_reserved_cents("ws-1", None) == 0


def test_reserve_accounts_committed(ledger):
    """A reservation must fit inside ``cap - committed``, not the raw cap."""
    from app.core.budget_ledger import BudgetDecision
    decision, _ = ledger.reserve(
        workspace_id="ws-1", ai_tool=None,
        estimated_cents=100, cap_cents=1_000, committed_cents=950,
    )
    assert decision == BudgetDecision.EXCEEDED
    decision, _ = ledger.reserve(
        workspace_id="ws-1", ai_tool=None,
        estimated_cents=50, cap_cents=1_000, committed_cents=950,
    )
    assert decision == BudgetDecision.ACCEPTED


def test_release_refunds_reserved(ledger):
    _, res = ledger.reserve(
        workspace_id="ws-1", ai_tool=None,
        estimated_cents=300, cap_cents=1_000, committed_cents=0,
    )
    assert ledger.current_reserved_cents("ws-1", None) == 300

    ledger.release(res)
    assert ledger.current_reserved_cents("ws-1", None) == 0


def test_release_clamps_at_zero(ledger):
    """Double-release should not push the counter negative."""
    _, res = ledger.reserve(
        workspace_id="ws-1", ai_tool=None,
        estimated_cents=100, cap_cents=1_000, committed_cents=0,
    )
    ledger.release(res)
    ledger.release(res)  # extra release — safe
    assert ledger.current_reserved_cents("ws-1", None) == 0


def test_zero_cost_reservation_skips_redis(ledger):
    """Estimated-cost of zero returns ACCEPTED without hitting Redis —
    a call to ``evaluate`` with no cost estimate should never fail
    because the ledger has nothing to do."""
    from app.core.budget_ledger import BudgetDecision
    decision, res = ledger.reserve(
        workspace_id="ws-1", ai_tool=None,
        estimated_cents=0, cap_cents=100, committed_cents=0,
    )
    assert decision == BudgetDecision.ACCEPTED
    assert res.estimated_cents == 0
    # Counter untouched.
    assert ledger.current_reserved_cents("ws-1", None) == 0


# ── Per-tool scoping ────────────────────────────────────────────────

def test_per_tool_reservations_isolated(ledger):
    """A per-tool budget for Codex must not block Claude reservations
    (existing #F3 cross-tool-bleed invariant)."""
    from app.core.budget_ledger import BudgetDecision

    d1, _ = ledger.reserve(
        workspace_id="ws-1", ai_tool="codex",
        estimated_cents=100, cap_cents=100, committed_cents=0,
    )
    assert d1 == BudgetDecision.ACCEPTED

    # Codex is now at cap. Claude must still be reservable.
    d2, _ = ledger.reserve(
        workspace_id="ws-1", ai_tool="claude",
        estimated_cents=100, cap_cents=100, committed_cents=0,
    )
    assert d2 == BudgetDecision.ACCEPTED

    # But a second Codex reservation must refuse.
    d3, _ = ledger.reserve(
        workspace_id="ws-1", ai_tool="codex",
        estimated_cents=100, cap_cents=100, committed_cents=0,
    )
    assert d3 == BudgetDecision.EXCEEDED


def test_workspace_reservations_isolated(ledger):
    from app.core.budget_ledger import BudgetDecision
    d1, _ = ledger.reserve(
        workspace_id="ws-a", ai_tool=None,
        estimated_cents=1_000, cap_cents=1_000, committed_cents=0,
    )
    assert d1 == BudgetDecision.ACCEPTED
    d2, _ = ledger.reserve(
        workspace_id="ws-b", ai_tool=None,
        estimated_cents=1_000, cap_cents=1_000, committed_cents=0,
    )
    assert d2 == BudgetDecision.ACCEPTED


# ── The atomicity property (the whole point of this PR) ─────────────

def test_concurrent_reserves_never_overshoot_cap(ledger):
    """Fifty threads each try to reserve 100 cents against a 1000-cent
    cap. Exactly 10 must succeed. Under a broken (non-atomic)
    implementation, N-1 concurrent threads could all read 'reserved=0'
    then all INCR — reserved ends at 5000 cents against a 1000 cap.

    This is the invariant governance-under-load #2057 requires."""
    from app.core.budget_ledger import BudgetDecision

    threads_count = 50
    per_reservation = 100
    cap = 1_000

    outcomes: list[BudgetDecision] = []
    lock = threading.Lock()

    def _worker():
        decision, _ = ledger.reserve(
            workspace_id="ws-c", ai_tool=None,
            estimated_cents=per_reservation,
            cap_cents=cap,
            committed_cents=0,
        )
        with lock:
            outcomes.append(decision)

    threads = [threading.Thread(target=_worker) for _ in range(threads_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    accepted = outcomes.count(BudgetDecision.ACCEPTED)
    exceeded = outcomes.count(BudgetDecision.EXCEEDED)

    assert accepted == cap // per_reservation, (
        f"expected exactly {cap // per_reservation} accepted, got {accepted}"
    )
    assert exceeded == threads_count - accepted
    assert ledger.current_reserved_cents("ws-c", None) == cap, (
        "reserved counter overshot the cap — atomicity is broken"
    )


def test_release_during_contention_frees_capacity(ledger):
    """Reserve to the cap. Release one. A subsequent reserve must
    succeed. Proves the release actually returns capacity to the pool,
    not just decrements a counter that reserve does not observe."""
    from app.core.budget_ledger import BudgetDecision

    results: list = []
    for _ in range(10):
        decision, res = ledger.reserve(
            workspace_id="ws-d", ai_tool=None,
            estimated_cents=100, cap_cents=1_000, committed_cents=0,
        )
        results.append((decision, res))

    # At-cap.
    d, _ = ledger.reserve(
        workspace_id="ws-d", ai_tool=None,
        estimated_cents=100, cap_cents=1_000, committed_cents=0,
    )
    assert d == BudgetDecision.EXCEEDED

    # Release one.
    ledger.release(results[0][1])

    # Now there is room.
    d, _ = ledger.reserve(
        workspace_id="ws-d", ai_tool=None,
        estimated_cents=100, cap_cents=1_000, committed_cents=0,
    )
    assert d == BudgetDecision.ACCEPTED


# ── Failure mode: Redis down ────────────────────────────────────────

def test_redis_down_returns_redis_down(monkeypatch):
    """Ledger with a Redis client that always raises on eval must
    return REDIS_DOWN, not overshoot the cap and not raise to the
    caller."""
    from app.core.budget_ledger import BudgetLedger, BudgetDecision

    class _BrokenClient:
        def eval(self, *a, **kw):
            raise ConnectionError("redis unreachable")

        def get(self, *a, **kw):
            raise ConnectionError("redis unreachable")

    broken = BudgetLedger(redis_client=_BrokenClient())
    decision, res = broken.reserve(
        workspace_id="ws-1", ai_tool=None,
        estimated_cents=100, cap_cents=1_000, committed_cents=0,
    )
    assert decision == BudgetDecision.REDIS_DOWN
    assert res is None
    # current_reserved read must also degrade to 0, not raise.
    assert broken.current_reserved_cents("ws-1", None) == 0


# ── Observability ───────────────────────────────────────────────────

def test_stats_track_outcomes(ledger):
    from app.core.budget_ledger import BudgetDecision
    for _ in range(3):
        ledger.reserve(
            workspace_id="ws-e", ai_tool=None,
            estimated_cents=100, cap_cents=200, committed_cents=0,
        )
    stats = ledger.stats()
    assert stats["reservations_accepted"] == 2
    assert stats["reservations_exceeded"] == 1


# ── Singleton API ───────────────────────────────────────────────────

def test_singleton_lifecycle():
    from app.core.budget_ledger import (
        get_budget_ledger,
        reset_budget_ledger_for_tests,
    )
    a = get_budget_ledger()
    b = get_budget_ledger()
    assert a is b
    reset_budget_ledger_for_tests()
    c = get_budget_ledger()
    assert c is not a
