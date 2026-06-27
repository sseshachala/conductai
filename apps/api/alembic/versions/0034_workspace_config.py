"""workspace_config table for platform-level per-workspace settings

Revision ID: 0034_workspace_config
Revises: 0033_users_setup_completed_at
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0034_workspace_config"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_config",
        sa.Column("id",           UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key",          sa.String(200), nullable=False),
        sa.Column("value",        sa.String,      nullable=True),
        sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at",   sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_workspace_config_ws_key", "workspace_config", ["workspace_id", "key"])
    op.create_index("ix_workspace_config_workspace_id", "workspace_config", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("workspace_config")
