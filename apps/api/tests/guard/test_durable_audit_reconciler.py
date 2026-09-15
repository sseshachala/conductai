"""Phase 4 of #1959 — reconciler regression harness.

Locks the four invariants Phase 5's contract-test gate will assert on
before flipping the feature flag in prod:

1. An 'accepted' row past its lease flips to 'orphaned'.
2. An 'accepted' row whose lease still has time left is untouched.
3. A 'finalized' row never regresses — the WHERE clause on the UPDATE
   is the safety property that keeps Phase 4 sound.
4. The batch cap is respected so a runaway orphan-burst can't lock
   the table for an unbounded window.

Uses a mocked session so we can inspect the generated SQL + parameter
bindings without touching Postgres. The actual UPDATE runs against real
data during CI's alembic round-trip; this suite locks the code contract.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.modules.guard.durable_audit_reconciler import (
    DEFAULT_MAX_BATCH,
    reconcile_orphaned,
)


class _CapturingSession:
    """Session double that snapshots the compiled SQL + params."""

    def __init__(self, rowcount: int = 3):
        self.last_sql: str | None = None
        self.last_params: dict | None = None
        self._rowcount = rowcount
        self.committed = False
        self.rolled_back = False

    def execute(self, stmt, params):
        self.last_sql = str(stmt)
        self.last_params = params
        result = MagicMock()
        result.rowcount = self._rowcount
        return result

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def test_reconcile_flips_accepted_rows_to_orphaned():
    sess = _CapturingSession(rowcount=5)
    count = reconcile_orphaned(sess)
    assert count == 5
    assert sess.committed is True
    assert "orphaned" in sess.last_sql
    assert "lifecycle_state = 'accepted'" in sess.last_sql


def test_reconcile_scopes_to_workspace_when_provided():
    sess = _CapturingSession()
    reconcile_orphaned(sess, workspace_id="ws-abc")
    assert sess.last_params["workspace_id"] == "ws-abc"
    assert "workspace_id = CAST(:workspace_id AS uuid)" in sess.last_sql


def test_reconcile_scans_every_workspace_when_id_absent():
    """Background daemon passes workspace_id=None — scan every workspace
    in one pass. The predicate is omitted entirely; RLS doesn't run in
    the worker context because there's no per-request session yet."""
    sess = _CapturingSession()
    reconcile_orphaned(sess)
    assert "workspace_id" not in (sess.last_params or {})
    assert "CAST(:workspace_id" not in sess.last_sql


def test_reconcile_never_touches_finalized_rows():
    """The safety invariant Phase 4 depends on. Both the candidate CTE
    filter AND the UPDATE's WHERE clause pin lifecycle_state='accepted'
    so a concurrently-finalized row is never regressed."""
    sess = _CapturingSession()
    reconcile_orphaned(sess)
    # Two occurrences: one in the SELECT WHERE, one in the UPDATE WHERE.
    assert sess.last_sql.count("lifecycle_state = 'accepted'") == 2


def test_reconcile_only_targets_expired_leases():
    """A row still within its lease MUST NOT be flipped. Verified via
    the SELECT WHERE clause containing lease_expires_at < now()."""
    sess = _CapturingSession()
    reconcile_orphaned(sess)
    assert "lease_expires_at < now()" in sess.last_sql
    assert "lease_expires_at IS NOT NULL" in sess.last_sql


def test_reconcile_respects_max_batch_cap():
    sess = _CapturingSession()
    reconcile_orphaned(sess, max_batch=42)
    assert sess.last_params["max_batch"] == 42
    assert "LIMIT :max_batch" in sess.last_sql


def test_default_batch_cap_is_500():
    """Locks the tuned default so a silent bump doesn't happen without
    a corresponding load-test PR."""
    sess = _CapturingSession()
    reconcile_orphaned(sess)
    assert sess.last_params["max_batch"] == DEFAULT_MAX_BATCH == 500


def test_reconcile_uses_skip_locked_to_avoid_worker_contention():
    """Multiple worker instances (Render horizontally scaled, or a
    manual re-run alongside the daemon) must not block each other.
    FOR UPDATE SKIP LOCKED lets each pass grab a fresh slice."""
    sess = _CapturingSession()
    reconcile_orphaned(sess)
    assert "FOR UPDATE SKIP LOCKED" in sess.last_sql


def test_reconcile_orders_by_lease_expires_ascending():
    """When the reconciler is behind (large orphan backlog), the
    longest-expired rows get flipped first so the Flight Recorder UI
    stops lying about them soonest."""
    sess = _CapturingSession()
    reconcile_orphaned(sess)
    assert "ORDER BY lease_expires_at ASC" in sess.last_sql


def test_reconcile_stamps_finalized_at_when_flipping():
    """Even though the row is orphaned rather than finalized, we set
    finalized_at so downstream duration/latency analytics have a
    non-null endpoint. COALESCE preserves any pre-existing value in
    case a partial finalize snuck in."""
    sess = _CapturingSession()
    reconcile_orphaned(sess)
    assert "finalized_at    = COALESCE(e.finalized_at, now())" in sess.last_sql


def test_reconcile_rolls_back_on_failure():
    class _Blowup(_CapturingSession):
        def execute(self, stmt, params):
            raise RuntimeError("simulated deadlock")

    sess = _Blowup()
    import pytest

    with pytest.raises(RuntimeError):
        reconcile_orphaned(sess)
    assert sess.rolled_back is True
    assert sess.committed is False


def test_reconcile_returns_zero_when_nothing_matched():
    sess = _CapturingSession(rowcount=0)
    assert reconcile_orphaned(sess) == 0
