"""Shared fixtures + stubs for the budget-ledger proofs.

Used by ``test_budget_ledger.py`` and ``test_budget_ledger_multi_scope.py``.
"""
from __future__ import annotations

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

    def exists(self):
        # PR 4 P1-C: budget_ledger.reconcile builds a NOT EXISTS
        # subquery against the receipts table to skip pre-cutover audit
        # rows that already have a settleable receipt. The stub
        # returns a marker object with ``~`` support so the SQLA
        # negation ``~q.exists()`` keeps working under the reconcile
        # path in tests that don't exercise the reconcile query.
        class _Exists:
            def __invert__(self):
                return self

            def __bool__(self):
                return False

        return _Exists()


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
        # Track for mirror-back on flush()/commit() so callers that read
        # ._rows post-commit see the mutations (Fix 9 test needs this).
        if not hasattr(self, "_live_shims"):
            self._live_shims = []
        self._live_shims.append(shim)
        return shim

    def flush(self) -> None:
        # Propagate shim mutations back to their backing rows so
        # callers reading self._rows see the ledger status changes.
        for shim in getattr(self, "_live_shims", []):
            backing = shim._backing_row
            backing.status = shim.status
            backing.actual_cents = shim.actual_cents
            backing.resolved_at = shim.resolved_at
        self._live_shims = []

    def commit(self) -> None:
        # Fix 9 (P2 #9): the ledger now commits() instead of flush()ing
        # on every durable-log write so rows survive the caller's
        # transaction lifecycle. In-memory stub: identical to flush()
        # — no actual transaction to commit here.
        self.flush()

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

def _reconcile(
    ledger, db, workspace_id, ai_tool, period_key, *,
    committed_cents=0, clerk_user_id=None, agent_identity_id=None,
):
    """Simulate the reconciler for a specific scope tuple.

    Fix 1 (P1 #1): keys are now scoped by (ws, user, agent, tool) so
    the helper accepts optional user/agent kwargs. Existing test cases
    pass only ai_tool -> (None, None, tool) which matches the pre-fix
    workspace-wide key shape.
    """
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
    _rk = _reserved_key(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period_key)
    _ck = _committed_key(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period_key)
    _hk = _res_hash_key(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period_key)
    _rd = _ready_key(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period_key)
    pipe.set(_ck, committed_cents, ex=ttl)
    pipe.delete(_rk)
    pipe.delete(_hk)
    if reserved_total > 0:
        pipe.set(_rk, reserved_total, ex=ttl)
    if hash_payload:
        pipe.hset(_hk, mapping=hash_payload)
        pipe.expire(_hk, ttl)
    pipe.set(_rd, "1", ex=ttl)
    pipe.execute()


# ── Helpers ─────────────────────────────────────────────────────────

def _current_period() -> str:
    from app.core.budget_ledger import monthly_period_key
    return monthly_period_key()


# ── PR-A1 multi-scope helpers ───────────────────────────────────────

class _FakeBudget:
    """Minimal shape the ledger's reserve_all() reads. Matches the
    ``GuardSpendBudget`` ORM object surface used inside reserve_all —
    no need to spin up the full ORM here."""
    def __init__(
        self,
        *,
        ai_tool: str | None = None,
        hard_cap_enabled: bool = True,
        hard_limit_usd: float | None = 1.0,
    ):
        self.ai_tool = ai_tool
        self.hard_cap_enabled = hard_cap_enabled
        self.hard_limit_usd = hard_limit_usd
