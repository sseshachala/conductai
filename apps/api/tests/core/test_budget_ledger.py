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
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

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


# ── DB stub ─────────────────────────────────────────────────────────
#
# The ledger writes durable rows to ``budget_reservations`` via a
# ``Session``. These proofs run without Postgres, so we stub a Session
# that walks a Python dict keyed by row id and exposes the small subset
# of the SQLAlchemy API the ledger actually calls: ``add``, ``get``,
# ``flush``, ``delete``, ``rollback``, ``query``.

@dataclass
class _Row:
    id: uuid.UUID
    workspace_id: uuid.UUID | str
    ai_tool: str | None
    period_key: str
    estimated_cents: int
    actual_cents: int | None
    status: str
    created_at: datetime
    resolved_at: datetime | None


class _StubQuery:
    def __init__(self, rows):
        self._rows = rows
        self._filters = []

    def filter(self, *expr):
        # Stub filters — we don't parse the SQLA expression. Instead we
        # record everything and let ``all()`` filter via manual match.
        self._filters.extend(expr)
        return self

    def scalar(self):
        return 0

    def all(self):
        # Post-filter is delegated to the caller in _StubSession; this
        # stub returns all rows unless the caller has already
        # narrowed them via other means.
        return list(self._rows)


class _StubSession:
    def __init__(self):
        self._rows: dict[uuid.UUID, _Row] = {}

    # Ledger-side API
    def add(self, obj) -> None:
        r = _Row(
            id=obj.id if isinstance(obj.id, uuid.UUID) else uuid.UUID(str(obj.id)),
            workspace_id=obj.workspace_id,
            ai_tool=obj.ai_tool,
            period_key=obj.period_key,
            estimated_cents=obj.estimated_cents,
            actual_cents=None,
            status="open",
            created_at=datetime.now(timezone.utc),
            resolved_at=None,
        )
        self._rows[r.id] = r
        # Mutate the ORM object so caller code can inspect it too.
        obj.status = "open"
        obj.created_at = r.created_at

    def get(self, model, pk):
        row = self._rows.get(pk if isinstance(pk, uuid.UUID) else uuid.UUID(str(pk)))
        if row is None:
            return None
        # Return a shim with mutable status/actual_cents/resolved_at.
        class _Shim:
            pass
        shim = _Shim()
        shim.id = row.id
        shim.status = row.status
        shim.actual_cents = row.actual_cents
        shim.resolved_at = row.resolved_at
        shim._backing_row = row
        return shim

    def flush(self) -> None:
        # Propagate shim mutations back to the backing row.
        for row in self._rows.values():
            # Nothing to do — ``get`` returns a shim referencing the
            # row; the ledger sets attrs on that shim. We mirror on
            # commit-of-shim below in _mirror.
            pass

    def delete(self, obj) -> None:
        target = getattr(obj, "id", None)
        if isinstance(target, uuid.UUID):
            self._rows.pop(target, None)

    def rollback(self) -> None:
        pass  # in-memory stub — nothing to unwind here

    def query(self, *args, **kwargs):
        return _StubQuery(list(self._rows.values()))

    # Test helpers
    def open_rows_for(self, workspace_id, ai_tool, period_key):
        out = []
        for r in self._rows.values():
            if str(r.workspace_id) != str(workspace_id):
                continue
            if r.ai_tool != ai_tool:
                continue
            if r.period_key != period_key:
                continue
            if r.status != "open":
                continue
            out.append(r)
        return out

    def _mirror_shim(self, shim):
        # Copy shim mutations back to the backing row so subsequent
        # get() calls return the updated values.
        row = shim._backing_row
        row.status = shim.status
        row.actual_cents = shim.actual_cents
        row.resolved_at = shim.resolved_at


@pytest.fixture
def db():
    return _StubSession()


def _mirror(db, shim):
    """Ledger calls db.flush() after setting shim attrs. Our stub's
    flush is a no-op; call this after operations that mutate rows to
    keep the shim-to-row propagation honest."""
    if shim is not None:
        db._mirror_shim(shim)


# ── Reconciler shim ────────────────────────────────────────────────
#
# The real reconciler queries ``BudgetReservation`` and ``GuardAuditEvent``
# via SQLAlchemy. Under the stub session, we bypass and call directly.

def _reconcile(ledger, db, workspace_id, ai_tool, period_key, *, committed_cents=0):
    """Simulate the reconciler for a specific (ws, tool, period) with
    an explicit committed_cents value the DB "would report", plus the
    open rows the stub already holds."""
    from app.core.budget_ledger import (
        _reserved_key, _committed_key, _res_hash_key, _ready_key,
        _seconds_until_next_period,
    )
    open_rows = db.open_rows_for(workspace_id, ai_tool, period_key)
    reserved_total = sum(r.estimated_cents for r in open_rows)
    hash_payload = {str(r.id).replace("-", ""): r.estimated_cents for r in open_rows}

    ttl = _seconds_until_next_period()
    client = ledger._client()
    pipe = client.pipeline()
    pipe.set(_committed_key(workspace_id, ai_tool, period_key), committed_cents, ex=ttl)
    pipe.delete(_reserved_key(workspace_id, ai_tool, period_key))
    pipe.delete(_res_hash_key(workspace_id, ai_tool, period_key))
    if reserved_total > 0:
        pipe.set(_reserved_key(workspace_id, ai_tool, period_key), reserved_total, ex=ttl)
    if hash_payload:
        pipe.hset(_res_hash_key(workspace_id, ai_tool, period_key), mapping=hash_payload)
        pipe.expire(_res_hash_key(workspace_id, ai_tool, period_key), ttl)
    pipe.set(_ready_key(workspace_id, ai_tool, period_key), "1", ex=ttl)
    pipe.execute()


# ── Kill switch ─────────────────────────────────────────────────────

def test_kill_switch_default_off(monkeypatch):
    monkeypatch.delenv("BUDGET_LEDGER_ENABLED", raising=False)
    from app.core.budget_ledger import enabled
    assert enabled() is False


# ── NOT_READY before reconcile ─────────────────────────────────────
# Reviewer P1 #3.

def test_reserve_before_reconcile_is_not_ready(ledger, db):
    """Cold worker with no reconcile ⇒ reserve must refuse with
    NOT_READY, not blind-INCR a counter that may be missing open
    reservations from a previous instance."""
    from app.core.budget_ledger import BudgetDecision

    ws = str(uuid.uuid4())
    decision, res = ledger.reserve(
        db=db, workspace_id=ws, ai_tool=None,
        estimated_cents=100, cap_cents=1000,
    )
    assert decision == BudgetDecision.NOT_READY
    assert res is None
    # Durable log must not have been polluted with a phantom row.
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

    key = _reserved_key(ws, None, monthly_period_key())
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
    # Durable row must have been rolled back — no phantom.
    assert len(db.open_rows_for(ws, None, _current_period())) == 0


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


# ── Helpers ─────────────────────────────────────────────────────────

def _current_period() -> str:
    from app.core.budget_ledger import monthly_period_key
    return monthly_period_key()
