"""add token_encrypted to agent_run_tokens

Revision ID: 0047
Revises: 0046
Create Date: 2026-07-01

"""

from alembic import op
import sqlalchemy as sa

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_run_tokens",
        sa.Column("token_encrypted", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("agent_run_tokens", "token_encrypted")
