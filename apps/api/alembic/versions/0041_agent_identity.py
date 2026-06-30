"""create agent_identities table

Revision ID: 0041
Revises: 0040
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "agent_identities",
        sa.Column("id",              sa.String(36),              primary_key=True),
        sa.Column("workspace_id",    sa.UUID(as_uuid=True),      nullable=False),
        sa.Column("name",            sa.String(100),             nullable=False),
        sa.Column("provider",        sa.String(50),              nullable=False, server_default="conduct"),
        sa.Column("token_prefix",    sa.String(30),              nullable=False),
        sa.Column("token_encrypted", sa.Text(),                  nullable=False),
        sa.Column("created_at",      sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at",    sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_agent_identities_workspace_id",
        "agent_identities",
        ["workspace_id"],
    )


def downgrade():
    op.drop_index("ix_agent_identities_workspace_id", table_name="agent_identities")
    op.drop_table("agent_identities")
