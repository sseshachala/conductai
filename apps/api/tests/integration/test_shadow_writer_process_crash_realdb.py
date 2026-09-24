"""Real-DB integration for process-crash recovery (#2209 PR 2).

Nightly-only per project convention — set ``RUN_ACCOUNTING_REALDB=1``.

Simulates a worker killed mid-request between audit-write and
shadow-write. Verifies the reconciler backfills the missing receipt on
the next scan. Also verifies mid-transaction failures leave no orphan
partial rows behind (atomic commit semantics preserved).
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_ACCOUNTING_REALDB") != "1",
    reason="Real-DB test — set RUN_ACCOUNTING_REALDB=1 (nightly only).",
)


@pytest.fixture(scope="module")
def workspace_id() -> str:
    from app.core.database import SessionLocal
    from sqlalchemy import text

    ws_id = str(uuid.uuid4())
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO workspaces (id, name, owner_id, is_approved, plan) "
                "VALUES (CAST(:id AS uuid), :name, :owner, true, 'free')"
            ),
            {"id": ws_id, "name": f"crash-{ws_id[:8]}", "owner": "test-realdb"},
        )
        db.commit()
    yield ws_id
    with SessionLocal() as db:
        db.execute(
            text(
                "DELETE FROM llm_attempt_receipts "
                "WHERE workspace_id = CAST(:id AS uuid)"
            ),
            {"id": ws_id},
        )
        db.execute(
            text(
                "DELETE FROM guard_audit_events "
                "WHERE workspace_id = CAST(:id AS uuid)"
            ),
            {"id": ws_id},
        )
        db.execute(
            text("DELETE FROM workspaces WHERE id = CAST(:id AS uuid)"),
            {"id": ws_id},
        )
        db.commit()


def _receipt_source(request_id: uuid.UUID) -> str | None:
    from app.core.database import SessionLocal
    from sqlalchemy import text

    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT source FROM llm_attempt_receipts "
                "WHERE request_id = :r LIMIT 1"
            ),
            {"r": str(request_id)},
        ).first()
    return row.source if row else None


def test_reconciler_backfills_when_shadow_writer_crashed(monkeypatch, workspace_id):
    """Simulates: worker wrote a guard_audit_events row, then crashed
    before shadow_write could run. Reconciler on next pass MUST detect
    the gap and insert a placeholder — that's the whole point of
    Session 6H's routing_meta-driven backfill."""
    import json as _json
    from app.core.database import SessionLocal
    from sqlalchemy import text
    from app.runtime.accounting import reconcile_missing_receipts

    req_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Insert the audit row without a matching receipt (simulated crash).
    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO guard_audit_events "
                "(id, workspace_id, request_id, provider, model, decision, "
                "ai_tool, clerk_user_id, ts, tokens_after, cost_usd_after, routing_meta) "
                "VALUES (gen_random_uuid(), CAST(:ws AS uuid), CAST(:rid AS uuid), "
                ":prov, :model, 'allowed', 'test', 'user_x', :ts, 42, 0.001, "
                "CAST(:meta AS jsonb))"
            ),
            {
                "ws": workspace_id,
                "rid": str(req_id),
                "prov": "anthropic",
                "model": "claude-sonnet-4-6",
                "ts": now,
                "meta": _json.dumps(
                    {
                        "operation": "messages.create",
                        "attempts": [
                            {
                                "succeeded": True,
                                "provider_or_integration": "anthropic",
                                "model": "claude-sonnet-4-6",
                            }
                        ],
                    }
                ),
            },
        )
        db.commit()

    # Pre-state: no receipt.
    assert _receipt_source(req_id) is None

    # Reconcile.
    result = reconcile_missing_receipts(
        workspace_id=workspace_id,
        period_start=now - timedelta(minutes=5),
        period_end=now + timedelta(minutes=5),
    )
    assert result.attempts_expected == 1
    assert result.receipts_written == 1

    # Post-state: placeholder present.
    assert _receipt_source(req_id) == "reconciler"


def test_persist_atomic_raise_leaves_no_partial_row(monkeypatch, workspace_id):
    """If _persist_atomic raises mid-write (simulating a worker killed
    partway through the INSERT), the row must NOT be visible after
    rollback. Postgres transaction semantics + our writer's session
    ownership guarantee this — the test verifies it end-to-end."""
    from app.core.database import SessionLocal
    from sqlalchemy import text
    from app.runtime.accounting.shadow_writer import _persist_atomic
    from app.models.llm_attempt_receipt import LlmAttemptReceipt

    req_id = uuid.uuid4()
    row = LlmAttemptReceipt(
        id=uuid.uuid4(),
        workspace_id=uuid.UUID(workspace_id),
        request_id=req_id,
        attempt_ordinal=0,
        contract_version=1,
        provider="anthropic",
        model="claude-sonnet-4-6",
        operation="messages.create",
        execution_outcome="succeeded",
        usage_origin="provider_reported",
        usage_completeness="complete",
        pricing_completeness="priced",
    )

    # Simulate a crash by rolling back before commit.
    db = SessionLocal()
    try:
        _persist_atomic(db, row, is_reconciler=False)
        db.rollback()  # simulated crash / kill signal
    finally:
        db.close()

    # No row should be visible after rollback.
    with SessionLocal() as verify_db:
        rows = verify_db.execute(
            text(
                "SELECT COUNT(*) FROM llm_attempt_receipts "
                "WHERE request_id = :r"
            ),
            {"r": str(req_id)},
        ).scalar_one()
    assert rows == 0


def test_reconciler_pagination_progresses_across_batches(monkeypatch, workspace_id):
    """Session 6J reviewer #2 fixed the stalled-pagination bug. Verify
    keyset cursors advance through > limit rows without rescanning."""
    import json as _json
    from app.core.database import SessionLocal
    from sqlalchemy import text
    from app.runtime.accounting import reconcile_missing_receipts

    # Seed 5 audit rows in a fresh sub-window, all missing shadow rows.
    now = datetime.now(timezone.utc)
    base_ts = now - timedelta(minutes=30)
    req_ids: list[uuid.UUID] = []
    with SessionLocal() as db:
        for i in range(5):
            rid = uuid.uuid4()
            req_ids.append(rid)
            db.execute(
                text(
                    "INSERT INTO guard_audit_events "
                    "(id, workspace_id, request_id, provider, model, decision, "
                    "ai_tool, clerk_user_id, ts, tokens_after, cost_usd_after, routing_meta) "
                    "VALUES (gen_random_uuid(), CAST(:ws AS uuid), CAST(:rid AS uuid), "
                    "'anthropic', 'claude-sonnet-4-6', 'allowed', 'test', 'user_x', "
                    ":ts, 10, 0.0001, CAST(:meta AS jsonb))"
                ),
                {
                    "ws": workspace_id,
                    "rid": str(rid),
                    "ts": base_ts + timedelta(seconds=i),
                    "meta": _json.dumps({"operation": "messages.create"}),
                },
            )
        db.commit()

    # limit=2 → should need 3 passes (2 + 2 + 1) with cursor advancing.
    cursor = None
    total_written = 0
    passes = 0
    while passes < 5:
        passes += 1
        result = reconcile_missing_receipts(
            workspace_id=workspace_id,
            period_start=base_ts - timedelta(seconds=1),
            period_end=base_ts + timedelta(minutes=1),
            limit=2,
            since_cursor=cursor,
        )
        total_written += result.receipts_written
        cursor = result.next_cursor
        if cursor is None:
            break

    assert total_written == 5
    assert cursor is None
    assert passes <= 4  # 5 rows / 2 per page = 3 useful passes
