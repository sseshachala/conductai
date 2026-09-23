"""Real-DB integration for llm_attempt_receipts (#2209 Session 6D).

Nightly-only per project convention — set ``RUN_ACCOUNTING_REALDB=1``.
Locks the DB contract the mocked tests only hint at:

- Model + migration 0148/0149/0150 apply cleanly against a live Postgres.
- Unique constraint on ``(request_id, attempt_ordinal)`` fires under a
  real duplicate insert (mocked tests use a MagicMock that only pretends).
- Concurrent inserts from two threads at the same (request_id, ordinal)
  produce exactly one row.
- Reconciler backfills a missing shadow row and marks it
  ``source="reconciler"``, ``usage_origin="reconciled"``.
- Workspace CASCADE delete drops the receipts.
"""

from __future__ import annotations

import os
import threading
import uuid
from datetime import datetime, timedelta, timezone

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_ACCOUNTING_REALDB") != "1",
    reason="Real-DB test — set RUN_ACCOUNTING_REALDB=1 (nightly only).",
)


# ─── Fixtures ─────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def workspace_id() -> str:
    """Seed a workspace row so the FK CASCADE test has real target rows."""
    from app.core.database import SessionLocal
    from sqlalchemy import text

    ws_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO workspaces (id, name, owner_id, is_approved, plan) "
                "VALUES (CAST(:id AS uuid), :name, :owner, true, 'free')"
            ),
            {"id": ws_id, "name": f"acct-realdb-{ws_id[:8]}", "owner": "test-realdb"},
        )
        db.commit()
    yield ws_id
    # workspace CASCADE takes the receipts with it — but be defensive.
    with SessionLocal() as db:
        db.execute(
            text(
                "DELETE FROM llm_attempt_receipts "
                "WHERE workspace_id = CAST(:id AS uuid)"
            ),
            {"id": ws_id},
        )
        db.execute(
            text("DELETE FROM workspaces WHERE id = CAST(:id AS uuid)"),
            {"id": ws_id},
        )
        db.commit()


def _shadow_on(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "guard_accounting_shadow_enabled", True)
    monkeypatch.setattr(settings, "guard_accounting_shadow_workspace_allowlist", "*")


def _receipt_count(request_id: uuid.UUID) -> int:
    from app.core.database import SessionLocal
    from sqlalchemy import text

    with SessionLocal() as db:
        return db.execute(
            text("SELECT COUNT(*) FROM llm_attempt_receipts WHERE request_id = :r"),
            {"r": str(request_id)},
        ).scalar_one()


# ─── Tests ────────────────────────────────────────────────────────────────


def test_shadow_write_persists_row(monkeypatch, workspace_id):
    _shadow_on(monkeypatch)
    from app.runtime.accounting.shadow_writer import shadow_write

    req_id = uuid.uuid4()
    rid = shadow_write(
        workspace_id=uuid.UUID(workspace_id),
        request_id=req_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":100,"output_tokens":50}}',
        legacy_input_tokens=100,
        legacy_output_tokens=50,
        legacy_cost_usd=0.001,
    )
    assert rid is not None
    assert _receipt_count(req_id) == 1


def test_unique_constraint_on_request_id_attempt_ordinal(monkeypatch, workspace_id):
    """Second insert at the same (request_id, attempt_ordinal) is swallowed."""
    _shadow_on(monkeypatch)
    from app.runtime.accounting.shadow_writer import shadow_write

    req_id = uuid.uuid4()
    rid1 = shadow_write(
        workspace_id=uuid.UUID(workspace_id),
        request_id=req_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',
        legacy_input_tokens=10,
        legacy_output_tokens=5,
        legacy_cost_usd=0.0001,
        attempt_ordinal=0,
    )
    rid2 = shadow_write(
        workspace_id=uuid.UUID(workspace_id),
        request_id=req_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":20,"output_tokens":10}}',
        legacy_input_tokens=20,
        legacy_output_tokens=10,
        legacy_cost_usd=0.0002,
        attempt_ordinal=0,  # SAME ordinal — must be rejected
    )
    assert rid1 is not None
    assert rid2 is None  # unique constraint fired, writer swallowed
    assert _receipt_count(req_id) == 1


def test_concurrent_duplicate_inserts_produce_one_row(monkeypatch, workspace_id):
    """Two threads racing on the same (request_id, ordinal) → one wins."""
    _shadow_on(monkeypatch)
    from app.runtime.accounting.shadow_writer import shadow_write

    req_id = uuid.uuid4()
    results: list = []
    barrier = threading.Barrier(2)

    def _worker():
        barrier.wait()
        rid = shadow_write(
            workspace_id=uuid.UUID(workspace_id),
            request_id=req_id,
            provider="anthropic",
            model="claude-sonnet-4-6",
            operation="messages.create",
            dispatched=True,
            response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',
            legacy_input_tokens=10,
            legacy_output_tokens=5,
            legacy_cost_usd=0.0001,
            attempt_ordinal=0,
        )
        results.append(rid)

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    non_none = [r for r in results if r is not None]
    assert len(non_none) == 1
    assert _receipt_count(req_id) == 1


def test_reconciler_backfills_missing_receipt(monkeypatch, workspace_id):
    """Insert a guard_audit_events row with no matching receipt, run
    reconciler, verify a placeholder receipt lands with source=reconciler."""
    from app.core.database import SessionLocal
    from sqlalchemy import text
    from app.runtime.accounting import reconcile_missing_receipts

    req_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO guard_audit_events "
                "(id, workspace_id, request_id, provider, model, decision, "
                "ai_tool, clerk_user_id, ts, tokens_after, cost_usd_after) "
                "VALUES (gen_random_uuid(), CAST(:ws AS uuid), CAST(:rid AS uuid), "
                ":prov, :model, 'allowed', 'test', 'user_x', :ts, 25, 0.001)"
            ),
            {
                "ws": workspace_id,
                "rid": str(req_id),
                "prov": "anthropic",
                "model": "claude-sonnet-4-6",
                "ts": now,  # bound to :ts placeholder (column also 'ts')
            },
        )
        db.commit()

    assert _receipt_count(req_id) == 0
    result = reconcile_missing_receipts(
        workspace_id=workspace_id,
        period_start=now - timedelta(minutes=5),
        period_end=now + timedelta(minutes=5),
    )
    assert result.receipts_written >= 1
    assert result.errors == 0
    assert _receipt_count(req_id) == 1

    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT source, usage_origin, execution_outcome "
                "FROM llm_attempt_receipts WHERE request_id = :r"
            ),
            {"r": str(req_id)},
        ).one()
        assert row.source == "reconciler"
        assert row.usage_origin == "reconciled"
        assert row.execution_outcome == "reconciled_late"


def test_reconciler_idempotent_on_repeat(monkeypatch, workspace_id):
    """Second reconciler pass on the same period writes nothing new."""
    from app.core.database import SessionLocal
    from sqlalchemy import text
    from app.runtime.accounting import reconcile_missing_receipts

    req_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO guard_audit_events "
                "(id, workspace_id, request_id, provider, model, decision, "
                "ai_tool, clerk_user_id, ts, tokens_after, cost_usd_after) "
                "VALUES (gen_random_uuid(), CAST(:ws AS uuid), CAST(:rid AS uuid), "
                ":prov, :model, 'allowed', 'test', 'user_x', :ts, 10, 0.0005)"
            ),
            {
                "ws": workspace_id,
                "rid": str(req_id),
                "prov": "openai",
                "model": "gpt-4.1",
                "ts": now,  # bound to :ts placeholder (column also 'ts')
            },
        )
        db.commit()

    r1 = reconcile_missing_receipts(
        workspace_id=workspace_id,
        period_start=now - timedelta(minutes=5),
        period_end=now + timedelta(minutes=5),
    )
    r2 = reconcile_missing_receipts(
        workspace_id=workspace_id,
        period_start=now - timedelta(minutes=5),
        period_end=now + timedelta(minutes=5),
    )
    assert r1.receipts_written >= 1
    assert r2.receipts_written == 0
    assert _receipt_count(req_id) == 1


def test_atomic_placeholder_promotion_survives_race(monkeypatch, workspace_id):
    """#2209 Session 6G reviewer #2 (#2221 review at 42d89898):
    reproduces the DELETE-then-INSERT race with two threads.

    Thread A: reconciler-source placeholder at (req, 0).
    Thread B: real gateway-source write at (req, 0), delayed slightly
              so A gets there first.

    Under the old DELETE-then-INSERT: A's placeholder was in place when
    B started. B's DELETE removed it, but if A ran between B's DELETE
    and B's INSERT, A re-inserted and B's INSERT would collide + be
    swallowed. Real data lost.

    With the atomic upsert: B's ``ON CONFLICT DO UPDATE ... WHERE
    source='reconciler'`` promotes A's placeholder to a real row
    regardless of ordering. Final row MUST have source='gateway'.
    """
    _shadow_on(monkeypatch)
    import threading
    from app.runtime.accounting.shadow_writer import shadow_write
    from app.core.database import SessionLocal
    from sqlalchemy import text

    req_id = uuid.uuid4()
    barrier = threading.Barrier(2)

    def _placeholder():
        barrier.wait()
        shadow_write(
            workspace_id=uuid.UUID(workspace_id),
            request_id=req_id,
            provider="anthropic",
            model="claude-sonnet-4-6",
            operation="reconciled",
            dispatched=True,
            response_bytes=None,
            legacy_input_tokens=None,
            legacy_output_tokens=None,
            legacy_cost_usd=None,
            attempt_ordinal=0,
            source="reconciler",
        )

    def _real():
        barrier.wait()
        shadow_write(
            workspace_id=uuid.UUID(workspace_id),
            request_id=req_id,
            provider="anthropic",
            model="claude-sonnet-4-6",
            operation="messages.create",
            dispatched=True,
            response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',
            legacy_input_tokens=10,
            legacy_output_tokens=5,
            legacy_cost_usd=0.0001,
            attempt_ordinal=0,
            source="gateway",
        )

    # Run several rounds — race outcome varies but final source must
    # always be 'gateway' regardless of which thread commits first.
    threads = [threading.Thread(target=_placeholder), threading.Thread(target=_real)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT source, total_input_tokens FROM llm_attempt_receipts "
                "WHERE request_id = :r AND attempt_ordinal = 0"
            ),
            {"r": str(req_id)},
        ).one()
    assert row.source == "gateway"
    # Promoted row has the real tokens, not the placeholder's None.
    assert row.total_input_tokens == 10


def test_reconciler_placeholder_never_overwrites_real_receipt(monkeypatch, workspace_id):
    """The reverse race: a real receipt exists; a concurrent reconciler
    pass must NOT overwrite it. ``ON CONFLICT DO NOTHING`` guarantees
    the real row stays put."""
    _shadow_on(monkeypatch)
    from app.runtime.accounting.shadow_writer import shadow_write
    from app.core.database import SessionLocal
    from sqlalchemy import text

    req_id = uuid.uuid4()
    # Real receipt first.
    shadow_write(
        workspace_id=uuid.UUID(workspace_id),
        request_id=req_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":42,"output_tokens":17}}',
        legacy_input_tokens=42,
        legacy_output_tokens=17,
        legacy_cost_usd=0.0002,
        attempt_ordinal=0,
        source="gateway",
    )
    # Reconciler tries to place a placeholder — must be a no-op.
    shadow_write(
        workspace_id=uuid.UUID(workspace_id),
        request_id=req_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="reconciled",
        dispatched=True,
        response_bytes=None,
        legacy_input_tokens=None,
        legacy_output_tokens=None,
        legacy_cost_usd=None,
        attempt_ordinal=0,
        source="reconciler",
    )
    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT source, total_input_tokens FROM llm_attempt_receipts "
                "WHERE request_id = :r AND attempt_ordinal = 0"
            ),
            {"r": str(req_id)},
        ).one()
    assert row.source == "gateway"
    assert row.total_input_tokens == 42


def test_workspace_delete_cascades_to_receipts(monkeypatch):
    """Verify the FK CASCADE on migration 0148 fires — orphan receipts
    would leak otherwise when a workspace is deleted."""
    _shadow_on(monkeypatch)
    from app.core.database import SessionLocal
    from sqlalchemy import text
    from app.runtime.accounting.shadow_writer import shadow_write

    ws_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO workspaces (id, name, owner_id, is_approved, plan) "
                "VALUES (CAST(:id AS uuid), :name, :owner, true, 'free')"
            ),
            {"id": ws_id, "name": f"cascade-{ws_id[:8]}", "owner": "test-realdb"},
        )
        db.commit()

    req_id = uuid.uuid4()
    shadow_write(
        workspace_id=uuid.UUID(ws_id),
        request_id=req_id,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        dispatched=True,
        response_bytes=b'{"usage":{"input_tokens":10,"output_tokens":5}}',
        legacy_input_tokens=10,
        legacy_output_tokens=5,
        legacy_cost_usd=0.0001,
    )
    assert _receipt_count(req_id) == 1

    with SessionLocal() as db:
        db.execute(
            text("DELETE FROM workspaces WHERE id = CAST(:id AS uuid)"),
            {"id": ws_id},
        )
        db.commit()

    assert _receipt_count(req_id) == 0
