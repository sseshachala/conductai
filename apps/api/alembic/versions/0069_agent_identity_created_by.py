"""add created_by_clerk_user_id to agent_identities

Revision ID: 0069
Revises: 0068
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_identities",
        sa.Column("created_by_clerk_user_id", sa.String(100), nullable=True),
    )


def downgrade():
    op.drop_column("agent_identities", "created_by_clerk_user_id")
