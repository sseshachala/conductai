"""guard_tool_executions: caller-reported tool executions keyed by correlation id (#2169)

Revision ID: 0170
Revises: 0169
Create Date: 2026-11-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0170"
down_revision = "0169"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guard_tool_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", sa.String(length=32), nullable=False),
        sa.Column("tool_use_id", sa.Text(), nullable=True),
        sa.Column("tool_name", sa.String(length=255), nullable=True),
        sa.Column("hook_session_id", sa.Text(), nullable=True),
        sa.Column("clerk_user_id", sa.Text(), nullable=True),
        sa.Column("execution_status", sa.String(length=20), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("correlation_source", sa.String(length=20), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"],
            name="fk_guard_tool_executions_workspace_id", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "correlation_id", name="uq_guard_tool_executions_ws_corr"),
    )


def downgrade() -> None:
    op.drop_table("guard_tool_executions")
