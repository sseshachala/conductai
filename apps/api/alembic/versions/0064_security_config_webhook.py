"""add slack_webhook_url to security_config

Revision ID: 0064
Revises: 0063
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0064"
down_revision = "0063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "security_config",
        sa.Column("slack_webhook_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("security_config", "slack_webhook_url")
