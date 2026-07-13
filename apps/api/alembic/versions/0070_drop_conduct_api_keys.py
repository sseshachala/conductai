"""drop conduct_api_keys table — retired in favour of agent_identities

Revision ID: 0070
Revises: 0069
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table("conduct_api_keys")


def downgrade():
    op.create_table(
        "conduct_api_keys",
        sa.Column("id",           sa.String(36),              primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True),         nullable=False),
        sa.Column("user_id",      sa.String(255),             nullable=False),
        sa.Column("name",         sa.String(100),             nullable=False),
        sa.Column("key_prefix",   sa.String(20),              nullable=False),
        sa.Column("key_hash",     sa.String(64),              nullable=False, unique=True),
        sa.Column("role",         sa.String(20),              nullable=False, server_default="developer"),
        sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at",   sa.DateTime(timezone=True), nullable=True),
    )
