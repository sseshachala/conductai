"""Add match_tokens_before_gt to guard_policies

Revision ID: 0011
Revises: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_policies", sa.Column("match_tokens_before_gt", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("guard_policies", "match_tokens_before_gt")
