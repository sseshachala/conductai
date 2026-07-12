"""agent_identity expires_at — 8h short-lived tokens

Revision ID: 0064
Revises: 0063
"""
from alembic import op
import sqlalchemy as sa

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "agent_identities",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("agent_identities", "expires_at")
