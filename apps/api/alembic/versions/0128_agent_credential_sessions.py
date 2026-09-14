"""Independent CLI and OAuth credential sessions.

Revision ID: 0128
Revises: 0127
"""
from alembic import op
import sqlalchemy as sa

revision = "0128"
down_revision = "0127"
branch_labels = None
depends_on = None


def upgrade():
    # Like agent_identities, authentication must look up credentials before
    # establishing workspace context. Only token hashes are stored here.
    op.create_table(
        "agent_credential_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("agent_identity_id", sa.String(36), nullable=False),
        sa.Column("access_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("refresh_token_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["agent_identity_id"], ["agent_identities.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_agent_credential_sessions_agent_identity_id", "agent_credential_sessions", ["agent_identity_id"])


def downgrade():
    op.drop_table("agent_credential_sessions")
