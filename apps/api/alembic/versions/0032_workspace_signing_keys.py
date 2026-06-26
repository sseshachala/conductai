"""workspace_signing_keys — per-workspace HMAC-SHA256 policy signing key

Adds a new table that stores a single signing key per workspace.
The key is generated server-side (32 random bytes). Only the fingerprint
(first 16 hex chars of sha256(key_bytes)) is ever returned after initial
generation. The raw key bytes are returned once at POST time so an admin
can write them to developer machines via `conduct guard install --signing-key`.

Revision ID: 0032
Revises: 0031
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import BYTEA


revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_signing_keys",
        sa.Column(
            "workspace_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("key_bytes", BYTEA, nullable=False),
        sa.Column("fingerprint", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("workspace_signing_keys")
