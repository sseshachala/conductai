"""mcp_servers — workspace-scoped MCP server registry

Revision ID: 0018
Revises: 0017
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", sa.UUID(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("environment_id", sa.UUID(), sa.ForeignKey("environments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("transport", sa.String(10), nullable=False, server_default="sse"),  # sse | http | stdio
        sa.Column("encrypted_auth", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.UniqueConstraint("workspace_id", "name", name="uq_mcp_server_name_per_workspace"),
    )
    op.create_index("ix_mcp_servers_workspace", "mcp_servers", ["workspace_id"])
    op.create_index("ix_mcp_servers_environment", "mcp_servers", ["environment_id"])


def downgrade() -> None:
    op.drop_table("mcp_servers")
