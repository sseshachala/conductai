"""guard: add enforcement_mode to guard_config

Revision ID: 0057
Revises: 0056
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE guard_config
        ADD COLUMN IF NOT EXISTS enforcement_mode VARCHAR(20) NOT NULL DEFAULT 'warn'
    """)


def downgrade():
    op.execute("ALTER TABLE guard_config DROP COLUMN IF EXISTS enforcement_mode")
