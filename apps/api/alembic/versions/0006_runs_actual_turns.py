"""Add actual_turns and budget_exhausted to runs for smart turn estimation

Revision ID: 0006
Revises: 0005
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("actual_turns", sa.Integer(), nullable=True))
    op.add_column("runs", sa.Column("budget_exhausted", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "budget_exhausted")
    op.drop_column("runs", "actual_turns")
