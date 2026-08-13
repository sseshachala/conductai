"""Concurrency probes — Group E of epic #1092.

Threaded/multi-connection tests that surface race conditions the
single-threaded pytest suite can't catch: SELECT FOR UPDATE contention,
Redis atomic increments, cache invalidation under parallel edits.

Starter suite: one canonical probe per pattern. Grow when a real
race bug lands (see feedback_security.md).

Marker `concurrency` so nightly can opt in via `-m concurrency`.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from app.core.database import SessionLocal
from app.models.workspace import Workspace


def _db_available() -> bool:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


requires_db = pytest.mark.skipif(not _db_available(), reason="Postgres not reachable")


@requires_db
@pytest.mark.concurrency
def test_parallel_workspace_insert_only_one_wins():
    """Ten workers race to insert the same Workspace row. One succeeds,
    nine hit IntegrityError. Zero rows corrupted."""
    ws_id = uuid.UUID("44444444-4444-4444-4444-000000000001")
    # Cleanup any previous run.
    with SessionLocal() as db:
        db.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": str(ws_id)})
        db.commit()

    now = datetime.now(timezone.utc)
    successes: list[int] = []
    failures: list[Exception] = []
    lock = threading.Lock()

    def attempt(worker_id: int) -> None:
        with SessionLocal() as db:
            try:
                db.add(Workspace(
                    id=ws_id, name=f"conc-{worker_id}", owner_id="conc-user",
                    plan="free", is_approved=True, created_at=now, updated_at=now,
                ))
                db.commit()
                with lock:
                    successes.append(worker_id)
            except Exception as exc:
                with lock:
                    failures.append(exc)

    threads = [threading.Thread(target=attempt, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(successes) == 1, f"expected exactly 1 winner, got {len(successes)}: {successes}"
    assert len(failures) == 9, f"expected 9 losers, got {len(failures)}"

    # And exactly one row exists.
    with SessionLocal() as db:
        row = db.execute(
            text("SELECT COUNT(*) FROM workspaces WHERE id = :id"),
            {"id": str(ws_id)},
        ).scalar_one()
        assert row == 1

    # Cleanup.
    with SessionLocal() as db:
        db.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": str(ws_id)})
        db.commit()


@requires_db
@pytest.mark.concurrency
def test_read_after_commit_visible_across_connections():
    """One connection commits, another connection reads immediately —
    row must be visible (default isolation should give us this, but
    a wrong pool setting could break it)."""
    ws_id = uuid.UUID("44444444-4444-4444-4444-000000000002")
    now = datetime.now(timezone.utc)

    with SessionLocal() as writer:
        writer.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": str(ws_id)})
        writer.commit()
        writer.add(Workspace(
            id=ws_id, name="conc-cross-conn", owner_id="conc-user",
            plan="free", is_approved=True, created_at=now, updated_at=now,
        ))
        writer.commit()

    with SessionLocal() as reader:
        row = reader.execute(
            text("SELECT name FROM workspaces WHERE id = :id"),
            {"id": str(ws_id)},
        ).fetchone()
        assert row is not None
        assert row.name == "conc-cross-conn"

    with SessionLocal() as writer:
        writer.execute(text("DELETE FROM workspaces WHERE id = :id"), {"id": str(ws_id)})
        writer.commit()
