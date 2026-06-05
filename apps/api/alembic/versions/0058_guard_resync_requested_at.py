"""guard: add resync_requested_at to guard_config

Revision ID: 0058
Revises: 0057
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0058"
down_revision = "0057"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE guard_config
        ADD COLUMN IF NOT EXISTS resync_requested_at TIMESTAMPTZ NULL
    """)


def downgrade():
    op.execute("ALTER TABLE guard_config DROP COLUMN IF EXISTS resync_requested_at")
