"""add token_prefix to agent_run_tokens

Revision ID: 0049
Revises: 0048
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_run_tokens",
        sa.Column("token_prefix", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_run_tokens", "token_prefix")
