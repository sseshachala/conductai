"""Phase 4 of #1959 — reconciler regression harness (code contract, mocked session).

Invariants asserted before the feature flag flips in prod:

1. An 'accepted' row past its lease flips to 'orphaned' (and is sealed into the chain).
2. A row whose lease still has time left is untouched (candidate scan filters on the lease).
3. A 'finalized' row never regresses: the candidate scan AND the per-row UPDATE pin
   lifecycle_state='accepted'.
4. The batch cap is respected.

The sealing itself (chain lock, ts, previous_hash, entry_hash) runs against PostgreSQL in
test_gateway_audit_chain_postgres.py; here the chain helpers are stubbed.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.modules.guard.durable_audit_reconciler import (
    DEFAULT_MAX_BATCH,
    reconcile_orphaned,
)

WS = "ef0a7e36-42a7-4968-9e6f-ee30d8e45383"
ROW = "22222222-2222-2222-2222-222222222222"

pytestmark = pytest.mark.usefixtures("stub_audit_chain")


class _CapturingSession:
    """First execute() is the candidate scan; later ones are per-row UPDATEs."""

    def __init__(self, candidates=1, update_rowcount: int = 1):
        self.statements: list[tuple[str, dict | None]] = []
        self._candidates = [(ROW, WS)] * candidates
        self._rowcount = update_rowcount
        self.committed = False
        self.rolled_back = False

    @property
    def scan_sql(self) -> str:
        return self.statements[0][0]

    @property
    def scan_params(self) -> dict:
        return self.statements[0][1]

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self.statements.append((sql, params))
        result = MagicMock()
        if sql.lstrip().startswith("SELECT"):
            result.fetchall.return_value = self._candidates
        elif "SET LOCAL" in sql:
            pass
        else:
            result.rowcount = self._rowcount
        return result

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def updates(self):
        return [s for s in self.statements if "UPDATE guard_audit_events" in s[0]]


def test_reconcile_flips_accepted_rows_to_orphaned_and_seals(stub_audit_chain):
    sess = _CapturingSession(candidates=2)
    assert reconcile_orphaned(sess) == 2
    assert sess.committed is True
    _, seal = stub_audit_chain
    assert seal.call_count == 2
    sql, params = sess.updates()[0]
    assert "'orphaned'" in sql and params["prev_hash"] == "prev" and params["hash_version"] == 3


def test_reconcile_scopes_to_workspace_when_provided():
    sess = _CapturingSession()
    reconcile_orphaned(sess, workspace_id="ws-abc")
    assert sess.scan_params["workspace_id"] == "ws-abc"
    assert "workspace_id = CAST(:workspace_id AS uuid)" in sess.scan_sql


def test_reconcile_scans_every_workspace_when_id_absent():
    sess = _CapturingSession()
    reconcile_orphaned(sess)
    assert "workspace_id" not in sess.scan_params
    assert "CAST(:workspace_id" not in sess.scan_sql


def test_reconcile_never_touches_finalized_rows():
    """Candidate scan and the per-row UPDATE both pin lifecycle_state='accepted'."""
    sess = _CapturingSession()
    reconcile_orphaned(sess)
    assert "lifecycle_state = 'accepted'" in sess.scan_sql
    assert "lifecycle_state = 'accepted'" in sess.updates()[0][0]


def test_reconcile_skips_and_does_not_seal_a_row_finalized_since_the_scan(stub_audit_chain):
    sess = _CapturingSession(update_rowcount=0)
    assert reconcile_orphaned(sess) == 0
    assert stub_audit_chain[1].call_count == 0


def test_reconcile_only_targets_expired_leases():
    sess = _CapturingSession()
    reconcile_orphaned(sess)
    assert "lease_expires_at < now()" in sess.scan_sql
    assert "lease_expires_at IS NOT NULL" in sess.scan_sql
    assert "lease_expires_at < now()" in sess.updates()[0][0]  # a renewed lease wins the race


def test_reconcile_respects_max_batch_cap():
    sess = _CapturingSession()
    reconcile_orphaned(sess, max_batch=42)
    assert sess.scan_params["max_batch"] == 42
    assert "LIMIT :max_batch" in sess.scan_sql


def test_default_batch_cap_is_500():
    sess = _CapturingSession()
    reconcile_orphaned(sess)
    assert sess.scan_params["max_batch"] == DEFAULT_MAX_BATCH == 500


def test_reconcile_orders_by_lease_expires_ascending():
    sess = _CapturingSession()
    reconcile_orphaned(sess)
    assert "ORDER BY lease_expires_at ASC" in sess.scan_sql


def test_reconcile_stamps_finalized_at_when_flipping():
    sess = _CapturingSession()
    reconcile_orphaned(sess)
    assert "COALESCE(finalized_at, :ts)" in sess.updates()[0][0]


def test_reconcile_rolls_back_on_failure():
    class _Blowup(_CapturingSession):
        def execute(self, stmt, params=None):
            raise RuntimeError("simulated deadlock")

    sess = _Blowup()
    with pytest.raises(RuntimeError):
        reconcile_orphaned(sess)
    assert sess.rolled_back is True
    assert sess.committed is False


def test_reconcile_returns_zero_when_nothing_matched():
    assert reconcile_orphaned(_CapturingSession(candidates=0)) == 0


def test_reconcile_stamps_decision_error_on_orphaned_rows():
    """Orphaned rows would keep the 'accepted' placeholder decision and read as normal traffic."""
    sess = _CapturingSession()
    reconcile_orphaned(sess)
    assert "decision        = 'error'" in sess.updates()[0][0]
