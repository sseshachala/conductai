"""Covering partial index for the per-identity activity rollup

GET /workspaces/{id}/agent-identities groups guard_audit_events by
agent_identity_id and counts distinct hook_session_id. The planner used the
single-column agent_identity_id index (random heap reads across all
workspaces, then an external-merge sort). This index is ordered by
(workspace_id, agent_identity_id, hook_session_id) with ts included, so the
group + count(distinct) streams without a sort.

CONCURRENTLY + IF NOT EXISTS (same pattern as 0167).

Revision ID: 0168
Revises: 0167
Create Date: 2026-10-08
"""
from __future__ import annotations

from alembic import op


revision = "0168"
down_revision = "0167"
branch_labels = None
depends_on = None

_NAME = "ix_guard_audit_events_ws_identity_session"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_NAME} ON guard_audit_events "
            "(workspace_id, agent_identity_id, hook_session_id) INCLUDE (ts) "
            "WHERE agent_identity_id IS NOT NULL AND hook_session_id IS NOT NULL AND hook_session_id <> ''"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_NAME}")
