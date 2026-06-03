"""guard: add last_alert_pct_bucket to deduplicate spend alerts

Revision ID: 0054
Revises: 0053
Create Date: 2026-06-03
"""
from alembic import op
import sqlalchemy as sa

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE guard_spend_budgets
        ADD COLUMN IF NOT EXISTS last_alert_pct_bucket INTEGER
    """)


def downgrade():
    op.execute("""
        ALTER TABLE guard_spend_budgets
        DROP COLUMN IF EXISTS last_alert_pct_bucket
    """)
