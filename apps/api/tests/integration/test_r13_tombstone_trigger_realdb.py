"""Real-DB integration for the R13 tombstone trigger (migration 0152).

The BEFORE DELETE trigger on ``agent_identities`` must copy the agent id
into ``budget_reservations.deleted_agent_identity_id`` before the FK's
SET NULL fires. Without a live Postgres the trigger cannot run, so the
existing shape-only test at ``tests/guard/test_r13_reservation_history_
tombstone.py`` cannot prove the population behaviour — this file does.

Nightly-only per project convention — set ``RUN_ACCOUNTING_REALDB=1``.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_ACCOUNTING_REALDB") != "1",
    reason="Real-DB test — set RUN_ACCOUNTING_REALDB=1 (nightly only).",
)


def test_agent_delete_tombstones_reservation_history():
    from app.core.database import SessionLocal
    from sqlalchemy import text

    ws_id = str(uuid.uuid4())
    agent_id = str(uuid.uuid4())
    reservation_id = str(uuid.uuid4())

    with SessionLocal() as db:
        db.execute(
            text(
                "INSERT INTO workspaces (id, name, owner_id, is_approved, plan) "
                "VALUES (CAST(:id AS uuid), :name, :owner, true, 'free')"
            ),
            {"id": ws_id, "name": f"r13-{ws_id[:8]}", "owner": "test-r13"},
        )
        db.execute(
            text(
                "INSERT INTO agent_identities (id, workspace_id, name, "
                "token_prefix, token_encrypted, created_at) "
                "VALUES (:id, CAST(:ws AS uuid), :name, :prefix, :ct, :now)"
            ),
            {
                "id": agent_id,
                "ws": ws_id,
                "name": "r13-doomed-agent",
                "prefix": f"r13_{agent_id[:8]}",
                "ct": "unused-encrypted-blob",
                "now": datetime.now(timezone.utc),
            },
        )
        db.execute(
            text(
                "INSERT INTO budget_reservations "
                "(id, workspace_id, agent_identity_id, period_key, "
                "estimated_cents, status, created_at) "
                "VALUES (CAST(:id AS uuid), CAST(:ws AS uuid), :agent, "
                ":period, 100, 'open', :now)"
            ),
            {
                "id": reservation_id,
                "ws": ws_id,
                "agent": agent_id,
                "period": "2026-09",
                "now": datetime.now(timezone.utc),
            },
        )
        db.commit()

        # Delete the agent — trigger must populate the tombstone before
        # the SET NULL cascade nulls agent_identity_id.
        db.execute(
            text("DELETE FROM agent_identities WHERE id = :id"),
            {"id": agent_id},
        )
        db.commit()

        row = db.execute(
            text(
                "SELECT agent_identity_id, deleted_agent_identity_id "
                "FROM budget_reservations WHERE id = CAST(:id AS uuid)"
            ),
            {"id": reservation_id},
        ).one()

        assert row.agent_identity_id is None, (
            "SET NULL FK did not fire — 0143 migration regressed."
        )
        assert row.deleted_agent_identity_id == agent_id, (
            "R13 trigger did not populate the tombstone. Migration 0152 "
            "may not have applied, or the trigger fires AFTER the FK "
            "cascade and can no longer read the original id."
        )

        # Cleanup — cascade via workspace so we do not need to remember
        # child tables the trigger might grow in future.
        db.execute(
            text("DELETE FROM workspaces WHERE id = CAST(:id AS uuid)"),
            {"id": ws_id},
        )
        db.commit()
