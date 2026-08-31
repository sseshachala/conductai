"""Add nullable runs.session_id + index — foundation for #1480 SSE surface.

Revision ID: 0108
Revises: 0107
Create Date: 2026-08-30

Only Lens-originated runs (from _execute_run_workflow) will set this; every
other trigger (workflow UI, CLI, webhooks, scheduler, security scanners,
nested runs) leaves it NULL. Pattern mirrors nullable agent_role_id.

No FK to glens_chat_sessions on purpose — session deletion must not
cascade run history. Index is for the worker's "runs I need to publish
events for" lookup by session.

Constraints/indexes named explicitly per project convention (Alembic
autogenerate is banned on this repo — hand-written names avoid drift).
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0108"
down_revision = "0107"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column("session_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_runs_session_id", "runs", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_runs_session_id", table_name="runs")
    op.drop_column("runs", "session_id")
