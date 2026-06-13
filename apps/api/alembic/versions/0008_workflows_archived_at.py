"""Soft delete for workflows — add archived_at column

Revision ID: 0008
Revises: 0007
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflows", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_workflows_archived_at", "workflows", ["archived_at"])


def downgrade() -> None:
    op.drop_index("ix_workflows_archived_at", table_name="workflows")
    op.drop_column("workflows", "archived_at")
