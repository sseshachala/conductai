"""agent_identity refresh token — 30d CLI re-auth without browser

Revision ID: 0065
Revises: 0064
"""
from alembic import op
import sqlalchemy as sa

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_identities",
        sa.Column("refresh_token_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "agent_identities",
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_agent_identities_refresh_token_hash",
        "agent_identities",
        ["refresh_token_hash"],
        unique=True,
        postgresql_where=sa.text("refresh_token_hash IS NOT NULL"),
    )


def downgrade():
    op.drop_index("ix_agent_identities_refresh_token_hash", table_name="agent_identities")
    op.drop_column("agent_identities", "refresh_token_expires_at")
    op.drop_column("agent_identities", "refresh_token_hash")
