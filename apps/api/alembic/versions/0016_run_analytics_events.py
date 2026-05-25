"""add run_analytics_events table for structured outcome logging

Revision ID: 0016
Revises: 0015
Create Date: 2026-05-25

One row per completed/failed run — feeds the benchmark, eval harness, and
cross-tenant analytics. No PII. No repo names. No code content.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "run_analytics_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.String(16), nullable=False),
        sa.Column("playbook_slug", sa.String(255), nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("trigger_type", sa.String(50), nullable=False),
        sa.Column("blocks_executed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tool_calls", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(50), nullable=False),
        sa.Column("human_verdict", sa.String(50), nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "ix_run_analytics_events_playbook_slug_created_at",
        "run_analytics_events", ["playbook_slug", "created_at"],
    )
    op.create_index(
        "ix_run_analytics_events_workspace_id_created_at",
        "run_analytics_events", ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_run_analytics_events_workspace_id_created_at", table_name="run_analytics_events")
    op.drop_index("ix_run_analytics_events_playbook_slug_created_at", table_name="run_analytics_events")
    op.drop_table("run_analytics_events")
