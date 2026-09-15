"""Real-DB integration test for the durable-audit lifecycle (#1990 B+C).

Runs against the Postgres service container in the nightly CI job.
Locks the end-to-end contract the unit-tests only hint at:

- insert_accepted() → row present with lifecycle_state='accepted'
- reconcile_orphaned() past-lease → row flips to 'orphaned', decision='error'
- finalize() concurrent with reconciler on the SAME row → exactly one wins

Not run per-PR to keep CI fast; nightly is enough for a regression
guard on the DB contract.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DURABLE_AUDIT_REALDB") != "1",
    reason="Real-DB test — set RUN_DURABLE_AUDIT_REALDB=1 (nightly only).",
)


# ─── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def workspace_id() -> str:
    """Seed a workspace row so foreign-key constraints on
    guard_audit_events don't reject the inserts."""
    from app.core.database import SessionLocal
    from sqlalchemy import text

    ws_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO workspaces (id, name, owner_id, is_approved, plan) "
                "VALUES (CAST(:id AS uuid), :name, :owner, true, 'free')"
            ),
            {"id": ws_id, "name": f"durable-audit-realdb-{ws_id[:8]}", "owner": "test-realdb"},
        )
        db.commit()
    yield ws_id
    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM guard_audit_events WHERE workspace_id = CAST(:id AS uuid)"),
            {"id": ws_id},
        )
        db.execute(text("DELETE FROM workspaces WHERE id = CAST(:id AS uuid)"), {"id": ws_id})
        db.commit()


def _accepted_row(workspace_id: str, *, lease_seconds: int = 60) -> str:
    """Write one 'accepted' row via the durable writer. Returns row_id."""
    from app.guard.audit import insert_accepted
    from app.core.database import SessionLocal

    with SessionLocal() as db:
        row_id = insert_accepted(
            workspace_id=workspace_id,
            clerk_user_id="realdb-user",
            ai_tool="claude-code",
            provider="anthropic",
            model="claude-sonnet",
            request_id=str(uuid.uuid4()),
            body={"messages": [{"role": "user", "content": "hi"}]},
            lease_seconds=lease_seconds,
        )
    return row_id


def _fetch_row(row_id: str) -> dict | None:
    """Read the row back via SQL so we can inspect the final state."""
    from app.core.database import SessionLocal
    from sqlalchemy import text

    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT lifecycle_state, decision, finalized_at, tokens_after "
                "FROM guard_audit_events WHERE id = CAST(:id AS uuid)"
            ),
            {"id": row_id},
        ).fetchone()
    return dict(row._mapping) if row else None


# ─── Item B — real-DB lifecycle end-to-end ────────────────────────────────


def test_accepted_row_flips_to_orphaned_past_lease(workspace_id: str):
    """The reconciler happy path against real Postgres:

        insert_accepted (lease=1s)
        wait 2s
        reconcile_orphaned
        assert row is orphaned + decision='error' + finalized_at set

    Fails if the migration + writer + reconciler triple ever drift out
    of sync — the class of bug the mocked unit-tests can't catch.
    """
    from app.modules.guard.durable_audit_reconciler import reconcile_orphaned
    from app.core.database import SessionLocal

    row_id = _accepted_row(workspace_id, lease_seconds=1)
    assert _fetch_row(row_id)["lifecycle_state"] == "accepted"

    time.sleep(2)  # let the lease expire

    with SessionLocal() as db:
        flipped = reconcile_orphaned(db, workspace_id=workspace_id)
    assert flipped >= 1

    row = _fetch_row(row_id)
    assert row is not None
    assert row["lifecycle_state"] == "orphaned"
    assert row["decision"] == "error"
    assert row["finalized_at"] is not None


def test_valid_lease_row_untouched_by_reconciler(workspace_id: str):
    """Rows still within their lease MUST NOT be flipped. Locks the
    'lease_expires_at < now()' guard against a mistake that would
    prematurely orphan in-flight requests."""
    from app.modules.guard.durable_audit_reconciler import reconcile_orphaned
    from app.core.database import SessionLocal

    row_id = _accepted_row(workspace_id, lease_seconds=300)  # 5 min

    with SessionLocal() as db:
        reconcile_orphaned(db, workspace_id=workspace_id)

    row = _fetch_row(row_id)
    assert row["lifecycle_state"] == "accepted", \
        "reconciler flipped a non-expired row — critical regression"


def test_reconciler_never_regresses_a_finalized_row(workspace_id: str):
    """Row is already 'finalized'. Reconciler must skip it entirely
    even if lease_expires_at happens to be in the past."""
    from app.guard.audit import finalize
    from app.modules.guard.durable_audit_reconciler import reconcile_orphaned
    from app.core.database import SessionLocal

    row_id = _accepted_row(workspace_id, lease_seconds=1)

    with SessionLocal() as db:
        finalize(
            row_id, workspace_id,
            decision="allowed",
            provider="anthropic",
            model="claude-sonnet",
            body={"messages": []},
            response_bytes=b'{"usage":{"input_tokens":1,"output_tokens":1}}',
            duration_ms=42,
        )

    time.sleep(2)  # past what the lease would have been

    with SessionLocal() as db:
        reconcile_orphaned(db, workspace_id=workspace_id)

    row = _fetch_row(row_id)
    assert row["lifecycle_state"] == "finalized", \
        "reconciler regressed a finalized row — WHERE clause failed"
    assert row["decision"] == "allowed"


# ─── Item C — concurrent finalize ↔ reconcile race ────────────────────────


def test_finalize_and_reconcile_never_both_succeed_on_same_row(workspace_id: str):
    """The narrow race: finalize() and reconcile_orphaned() hit the same
    row simultaneously. FOR UPDATE SKIP LOCKED + the WHERE clauses on
    both UPDATEs must guarantee exactly one flips the row.

    Runs both operations in parallel threads against a real Postgres
    session and asserts the invariant holds.
    """
    from app.guard.audit import finalize
    from app.modules.guard.durable_audit_reconciler import reconcile_orphaned
    from app.core.database import SessionLocal

    row_id = _accepted_row(workspace_id, lease_seconds=1)
    time.sleep(2)  # ensure the reconciler considers it expired

    results: dict[str, bool | int] = {}

    def _run_finalize():
        try:
            with SessionLocal() as db:
                results["finalize"] = finalize(
                    row_id, workspace_id,
                    decision="allowed",
                    provider="anthropic",
                    model="claude-sonnet",
                    body={"messages": []},
                    response_bytes=b'{"usage":{"input_tokens":1,"output_tokens":1}}',
                    duration_ms=42,
                )
        except Exception as e:
            results["finalize_err"] = str(e)

    def _run_reconcile():
        try:
            with SessionLocal() as db:
                results["reconcile"] = reconcile_orphaned(db, workspace_id=workspace_id)
        except Exception as e:
            results["reconcile_err"] = str(e)

    t1 = threading.Thread(target=_run_finalize)
    t2 = threading.Thread(target=_run_reconcile)
    t1.start(); t2.start()
    t1.join(); t2.join()

    row = _fetch_row(row_id)
    # Either finalize wins (final state 'finalized') or reconciler wins
    # (final state 'orphaned'). Both simultaneously succeeding would mean
    # two UPDATE statements each flipped the row from 'accepted' — the
    # invariant Phase 4 was designed to make impossible.
    assert row["lifecycle_state"] in ("finalized", "orphaned")
    if row["lifecycle_state"] == "finalized":
        assert results.get("finalize") is True
        # reconcile must have found nothing OR skipped via lock
        assert results.get("reconcile", 0) == 0
    else:
        assert results.get("reconcile", 0) >= 1
        # finalize must have returned False (rowcount=0)
        assert results.get("finalize") is False
