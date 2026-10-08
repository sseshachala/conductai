"""Indexes backing keyset paging + filtered Guard event lists

- guard_sessions (workspace_id, started_at)        -> GET /guard/spend/sessions
- guard_audit_events (workspace_id, rule_id, ts)   -> rule filter on /guard/events
- guard_audit_events (workspace_id, decision, ts)  -> decision filter on /guard/events
- session_reports (workspace_id, created_at)       -> GET /guard/session-reports

CONCURRENTLY + IF NOT EXISTS (same pattern as 0095) so the migration does not
lock prod tables and re-runs are safe.

Revision ID: 0167
Revises: 0166
Create Date: 2026-10-08
"""
from __future__ import annotations

from alembic import op


revision = "0167"
down_revision = "0166"
branch_labels = None
depends_on = None

_INDEXES = (
    ("ix_guard_sessions_ws_started", "guard_sessions", "workspace_id, started_at"),
    ("ix_guard_audit_events_ws_rule_ts", "guard_audit_events", "workspace_id, rule_id, ts"),
    ("ix_guard_audit_events_ws_decision_ts", "guard_audit_events", "workspace_id, decision, ts"),
    ("ix_session_reports_ws_created", "session_reports", "workspace_id, created_at"),
)


def upgrade() -> None:
    with op.get_context().autocommit_block():
        for name, table, cols in _INDEXES:
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({cols})")


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _table, _cols in _INDEXES:
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
