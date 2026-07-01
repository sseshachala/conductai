"""add agent_run_tokens table

Revision ID: 0045
Revises: 0044
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_run_tokens",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_identity_id", sa.String(36), nullable=True),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_agent_run_tokens_workspace_id", "agent_run_tokens", ["workspace_id"])
    op.create_index("ix_agent_run_tokens_run_id", "agent_run_tokens", ["run_id"])


def downgrade():
    op.drop_index("ix_agent_run_tokens_run_id", table_name="agent_run_tokens")
    op.drop_index("ix_agent_run_tokens_workspace_id", table_name="agent_run_tokens")
    op.drop_table("agent_run_tokens")
