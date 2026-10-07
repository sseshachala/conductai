"""PR 6d — atomic budget-reservation ledger proofs.

Covers the four issues reviewer surfaced on the initial draft:

- **P1 #1** — double release must not refund another reservation's slot.
  ``test_double_release_does_not_refund_other_reservation``.
- **P1 #2** — settlement must not depend on a caller-supplied stale
  committed snapshot. ``test_commit_moves_reserved_to_committed``,
  ``test_stale_committed_snapshot_cannot_leak_capacity``.
- **P1 #3** — Redis loss must not silently restore capacity.
  ``test_reserve_before_reconcile_is_not_ready``,
  ``test_reconciler_restores_reserved_from_durable_log``.
- **P2 #4** — partial release must preserve the counter's TTL.
  ``test_partial_release_preserves_ttl``.

Uses fakeredis[lua] so the Lua atomicity semantics match real Redis
(single-threaded script execution).
"""
from __future__ import annotations

import threading
import uuid


from ._budget_ledger_helpers import (  # noqa: F401 — fixtures
    _current_period,
    _reconcile,
    _reset_singletons,
    db,
    ledger,
    redis_client,
)
# ── Kill switch ─────────────────────────────────────────────────────


def test_kill_switch_default_off(monkeypatch):
    monkeypatch.delenv("BUDGET_LEDGER_ENABLED", raising=False)
    from app.core.budget_ledger import enabled
    assert enabled() is False


# ── NOT_READY before reconcile ─────────────────────────────────────
# Reviewer P1 #3.

def test_reserve_before_reconcile_self_heals(ledger, db):
    """Cold worker on a scope the startup reconciler never enumerated
    (new workspace, first hit ever) must self-heal by calling
    ``reconcile()`` inline once, not sit at NOT_READY forever.

    Before self-heal, prod gateways for brand-new workspaces returned
    503 ``budget_reservation_refused / not_ready`` on every request
    because the startup reconciler only enumerates scopes that already
    have rows in ``budget_reservations`` or ``guard_audit_events``.
    """
    from app.core.budget_ledger import BudgetDecision

    ws = str(uuid.uuid4())
    decision, res = ledger.reserve(
        db=db, workspace_id=ws, ai_tool=None,
        estimated_cents=100, cap_cents=1000,
    )
    assert decision == BudgetDecision.ACCEPTED
    assert res is not None
    # After self-heal, the durable row from THIS reserve is the only
    # open row for the scope.
    assert len(db.open_rows_for(ws, None, _current_period())) == 1


def test_reserve_stays_not_ready_when_self_heal_raises(ledger, db, monkeypatch):
    """If the inline reconcile itself blows up (DB unreachable etc.),
    the Lua's own :ready check must still fail-closed with NOT_READY.
    Never accept blind."""
    from app.core.budget_ledger import BudgetDecision

    def _boom(*a, **kw):
        raise RuntimeError("simulated DB outage during reconcile")

    monkeypatch.setattr(ledger, "reconcile", _boom)

    ws = str(uuid.uuid4())
    decision, res = ledger.reserve(
        db=db, workspace_id=ws, ai_tool=None,
        estimated_cents=100, cap_cents=1000,
    )
    assert decision == BudgetDecision.NOT_READY
    assert res is None
    # Phantom durable row from the failed attempt must be cleaned up.
    assert len(db.open_rows_for(ws, None, _current_period())) == 0


# ── Basic reserve/release with reservation identity ────────────────

def test_reserve_within_cap_accepted(ledger, db):
    from app.core.budget_ledger import BudgetDecision

    ws = str(uuid.uuid4())
    _reconcile(ledger, db, ws, None, _current_period())

    decision, res = ledger.reserve(
        db=db, workspace_id=ws, ai_tool=None,
        estimated_cents=100, cap_cents=10_000,
    )
    assert decision == BudgetDecision.ACCEPTED
    assert res is not None
    assert res.estimated_cents == 100
    assert ledger.current_reserved_cents(ws, None) == 100
    assert len(db.open_rows_for(ws, None, _current_period())) == 1


def test_reserve_over_cap_refused(ledger, db):
    from app.core.budget_ledger import BudgetDecision

    ws = str(uuid.uuid4())
    _reconcile(ledger, db, ws, None, _current_period())

    decision, res = ledger.reserve(
        db=db, workspace_id=ws, ai_tool=None,
        estimated_cents=200, cap_cents=100,
    )
    assert decision == BudgetDecision.EXCEEDED
    assert res is None
    assert ledger.current_reserved_cents(ws, None) == 0
    # Durable log must have deleted the row we speculatively inserted.
    assert len(db.open_rows_for(ws, None, _current_period())) == 0


# ── P1 #1: reservation identity — double release must not refund
# ── another reservation's slot.

def test_double_release_does_not_refund_other_reservation(ledger, db):
    """Reviewer's exact scenario:
    reserve A=40, reserve B=60, release A twice, then a third reserve
    of 40 must NOT succeed against a cap of 100 — B still owns 60,
    total should be 100."""
    ws = str(uuid.uuid4())
    _reconcile(ledger, db, ws, None, _current_period())

    from app.core.budget_ledger import BudgetDecision

    _, ra = ledger.reserve(db=db, workspace_id=ws, ai_tool=None,
                           estimated_cents=40, cap_cents=100)
    _, rb = ledger.reserve(db=db, workspace_id=ws, ai_tool=None,
                           estimated_cents=60, cap_cents=100)
    assert ra is not None and rb is not None
    assert ledger.current_reserved_cents(ws, None) == 100

    # First release of A refunds 40. Second release of A must be a no-op.
    ledger.release(db, ra)
    ledger.release(db, ra)
    assert ledger.current_reserved_cents(ws, None) == 60, (
        "double release refunded a second time — reservation identity broken"
    )

    # An 80-cent reserve must now refuse (60 already reserved by B).
    decision, _ = ledger.reserve(
        db=db, workspace_id=ws, ai_tool=None,
        estimated_cents=80, cap_cents=100,
    )
    assert decision == BudgetDecision.EXCEEDED


# ── P1 #2: settlement — commit converts reserved → committed
# ── atomically, no stale-snapshot race.

def test_commit_moves_reserved_to_committed(ledger, db):
    ws = str(uuid.uuid4())
    _reconcile(ledger, db, ws, None, _current_period())

    _, res = ledger.reserve(db=db, workspace_id=ws, ai_tool=None,
                            estimated_cents=100, cap_cents=1000)
    assert ledger.current_reserved_cents(ws, None) == 100
    assert ledger.current_committed_cents(ws, None) == 0

    ledger.commit(db, res, actual_cents=80)
    assert ledger.current_reserved_cents(ws, None) == 0
    assert ledger.current_committed_cents(ws, None) == 80


def test_stale_committed_snapshot_cannot_leak_capacity(ledger, db):
    """Reviewer P1 #2: reserve() no longer accepts a caller-supplied
    committed_cents. All three terms (reserved, committed, estimated)
    are read inside Lua so the check cannot race against a concurrent
    commit."""
    ws = str(uuid.uuid4())
    _reconcile(ledger, db, ws, None, _current_period())

    from app.core.budget_ledger import BudgetDecision

    # Fill the pool via commits (as if prior requests completed).
    for _ in range(9):
        _, r = ledger.reserve(db=db, workspace_id=ws, ai_tool=None,
                              estimated_cents=100, cap_cents=1000)
        assert r is not None
        ledger.commit(db, r, actual_cents=100)
    assert ledger.current_committed_cents(ws, None) == 900

    # A fresh reserve for 200 must refuse because committed(900) +
    # reserved(0) + 200 > 1000. The old-style caller-supplied stale
    # snapshot would have said "committed=800, room for 200" and
    # accepted.
    decision, _ = ledger.reserve(
        db=db, workspace_id=ws, ai_tool=None,
        estimated_cents=200, cap_cents=1000,
    )
    assert decision == BudgetDecision.EXCEEDED


def test_commit_is_idempotent_by_reservation_id(ledger, db):
    """Double commit must not double-count. Second call finds hash
    empty and no-ops."""
    ws = str(uuid.uuid4())
    _reconcile(ledger, db, ws, None, _current_period())

    _, res = ledger.reserve(db=db, workspace_id=ws, ai_tool=None,
                            estimated_cents=100, cap_cents=1000)
    ledger.commit(db, res, actual_cents=80)
    ledger.commit(db, res, actual_cents=80)  # duplicate
    assert ledger.current_committed_cents(ws, None) == 80


# ── P1 #3: Redis loss ⇒ reconciler must restore capacity from
# ── durable log.

def test_reconciler_restores_reserved_from_durable_log(ledger, db, redis_client):
    """The reviewer's flush scenario: reserve the cap, flush Redis,
    reconciler should refuse a new full-cap reserve because the
    durable log still shows the original outstanding."""
    ws = str(uuid.uuid4())
    _reconcile(ledger, db, ws, None, _current_period())

    from app.core.budget_ledger import BudgetDecision

    _, res = ledger.reserve(db=db, workspace_id=ws, ai_tool=None,
                            estimated_cents=1000, cap_cents=1000)
    assert res is not None

    # Redis flush loses in-flight state (reserved, committed, ready).
    redis_client.flushdb()

    # A blind reserve at this point must NOT_READY.
    decision, _ = ledger.reserve(
        db=db, workspace_id=ws, ai_tool=None,
        estimated_cents=1000, cap_cents=1000,
    )
    assert decision == BudgetDecision.NOT_READY

    # Reconciler replays open rows.
    _reconcile(ledger, db, ws, None, _current_period())

    # Now a reserve against the still-outstanding reservation must
    # refuse — the durable log recovery restored the counter.
    decision, _ = ledger.reserve(
        db=db, workspace_id=ws, ai_tool=None,
        estimated_cents=1000, cap_cents=1000,
    )
    assert decision == BudgetDecision.EXCEEDED


# ── P2 #4: partial release preserves TTL. ──────────────────────────

def test_partial_release_preserves_ttl(ledger, db, redis_client):
    from app.core.budget_ledger import _reserved_key, monthly_period_key

    ws = str(uuid.uuid4())
    _reconcile(ledger, db, ws, None, _current_period())

    _, ra = ledger.reserve(db=db, workspace_id=ws, ai_tool=None,
                           estimated_cents=100, cap_cents=1000)
    _, rb = ledger.reserve(db=db, workspace_id=ws, ai_tool=None,
                           estimated_cents=100, cap_cents=1000)

    key = _reserved_key(ws, None, None, None, monthly_period_key())
    ttl_before = redis_client.ttl(key)
    assert ttl_before > 0

    # Partial release — refunds ra only; rb still holds 100.
    ledger.release(db, ra)
    assert ledger.current_reserved_cents(ws, None) == 100

    ttl_after = redis_client.ttl(key)
    assert ttl_after > 0, (
        f"partial release left TTL={ttl_after} — SET without EXPIRE "
        "leaked the counter into a permanent key (reviewer P2 #4)"
    )


# ── Atomicity property — 50 concurrent reserves ─────────────────────

def test_concurrent_reserves_never_overshoot_cap(ledger, db):
    """The invariant governance-under-load #2057 requires. 50 threads
    race for 10 slots of 100 each against a 1000 cap — exactly 10
    accepted."""
    ws = str(uuid.uuid4())
    _reconcile(ledger, db, ws, None, _current_period())

    from app.core.budget_ledger import BudgetDecision

    outcomes = []
    outcomes_lock = threading.Lock()

    def _worker():
        decision, _ = ledger.reserve(
            db=db, workspace_id=ws, ai_tool=None,
            estimated_cents=100, cap_cents=1000,
        )
        with outcomes_lock:
            outcomes.append(decision)

    threads = [threading.Thread(target=_worker) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    accepted = outcomes.count(BudgetDecision.ACCEPTED)
    assert accepted == 10, f"expected 10 accepted, got {accepted}"
    assert ledger.current_reserved_cents(ws, None) == 1000


# ── Redis-down failure mode ─────────────────────────────────────────

def test_redis_down_returns_redis_down(db):
    from app.core.budget_ledger import BudgetLedger, BudgetDecision

    class _BrokenClient:
        def eval(self, *a, **kw):
            raise ConnectionError("down")

        def get(self, *a, **kw):
            raise ConnectionError("down")

    broken = BudgetLedger(redis_client=_BrokenClient())
    ws = str(uuid.uuid4())
    decision, res = broken.reserve(
        db=db, workspace_id=ws, ai_tool=None,
        estimated_cents=100, cap_cents=1000,
    )
    assert decision == BudgetDecision.REDIS_DOWN
    assert res is None
    # R8 fix (reviewer P1): a Redis exception is ambiguous. The
    # connection may have timed out AFTER the Lua script executed
    # and Redis holds the reservation. Preserve the durable row so
    # the reconciler can either confirm-and-mirror or classify-and-
    # release when it runs. Pre-R8 the row was deleted here — that
    # leaked capacity when Redis had actually applied but lost the
    # reply.
    open_rows = db.open_rows_for(ws, None, _current_period())
    assert len(open_rows) == 1, (
        "durable row must survive Redis exception so reconciler can "
        "resolve the ambiguous state — see R8"
    )
    assert open_rows[0].status == "open"


# ── Zero-cost bypass ────────────────────────────────────────────────

def test_zero_cost_reservation_skips_redis(ledger, db):
    from app.core.budget_ledger import BudgetDecision

    ws = str(uuid.uuid4())
    # Deliberately do NOT reconcile — zero-cost should short-circuit.
    decision, res = ledger.reserve(
        db=db, workspace_id=ws, ai_tool=None,
        estimated_cents=0, cap_cents=100,
    )
    assert decision == BudgetDecision.ACCEPTED
    assert res.estimated_cents == 0
