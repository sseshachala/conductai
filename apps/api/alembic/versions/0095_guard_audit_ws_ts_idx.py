"""Index guard_audit_events on (workspace_id, ts DESC)

Backs the tail-scan pattern used by guard_recent_activity and every
"last N events for workspace X" query. Uses CONCURRENTLY so the migration
does not lock the table in prod. IF NOT EXISTS so re-runs are safe.

Revision ID: 0095
Revises: 0094
Create Date: 2026-08-18
"""
from __future__ import annotations

from alembic import op


revision = "0095"
down_revision = "0094"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_guard_audit_events_ws_ts "
            "ON guard_audit_events (workspace_id, ts DESC)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS ix_guard_audit_events_ws_ts"
        )
