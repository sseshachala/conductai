"""0021 conduct api keys

Revision ID: 0021
Revises: 0020
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conduct_api_keys",
        sa.Column("id",           sa.String(36),  primary_key=True),
        sa.Column("workspace_id", sa.String(36),  nullable=False, index=True),
        sa.Column("user_id",      sa.String(255), nullable=False),
        sa.Column("name",         sa.String(100), nullable=False),
        sa.Column("key_prefix",   sa.String(20),  nullable=False),   # first 20 chars — display only
        sa.Column("key_hash",     sa.String(64),  nullable=False, unique=True),  # SHA-256 hex
        sa.Column("role",         sa.String(20),  nullable=False, server_default="editor"),
        sa.Column("created_at",   sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at",   sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_table("conduct_api_keys")
