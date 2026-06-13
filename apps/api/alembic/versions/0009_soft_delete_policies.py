"""Soft delete for guard_policies and security_policies — add archived_at

Revision ID: 0009
Revises: 0008
"""
from alembic import op
import sqlalchemy as sa

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_policies", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("security_policies", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("security_policies", "archived_at")
    op.drop_column("guard_policies", "archived_at")
