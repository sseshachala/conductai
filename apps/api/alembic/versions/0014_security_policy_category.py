"""add category column to security_policies

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("security_policies", sa.Column("category", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("security_policies", "category")
