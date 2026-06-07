"""guard: add token_guardrails, guardrail_snapshot, slack_webhook_url to guard_config

Revision ID: 0059
Revises: 0058
Create Date: 2026-06-06
"""
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE guard_config
        ADD COLUMN IF NOT EXISTS token_guardrails   JSONB   NULL,
        ADD COLUMN IF NOT EXISTS guardrail_snapshot JSONB   NULL,
        ADD COLUMN IF NOT EXISTS slack_webhook_url  VARCHAR NULL
    """)


def downgrade():
    op.execute("ALTER TABLE guard_config DROP COLUMN IF EXISTS token_guardrails")
    op.execute("ALTER TABLE guard_config DROP COLUMN IF EXISTS guardrail_snapshot")
    op.execute("ALTER TABLE guard_config DROP COLUMN IF EXISTS slack_webhook_url")
