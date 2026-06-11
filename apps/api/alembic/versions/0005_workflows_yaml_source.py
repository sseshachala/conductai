"""Add is_template and source columns to workflows — backfill for existing prod DBs
that were stamped at 0001 and didn't get these columns from the squashed baseline.

Revision ID: 0005
Revises: 0004
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE workflows
            ADD COLUMN IF NOT EXISTS is_template BOOLEAN NOT NULL DEFAULT false,
            ADD COLUMN IF NOT EXISTS source VARCHAR(32)
    """)


def downgrade() -> None:
    op.drop_column("workflows", "source")
    op.drop_column("workflows", "is_template")
