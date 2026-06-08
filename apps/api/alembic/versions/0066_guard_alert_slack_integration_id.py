"""add alert_slack_integration_id to guard_config

Revision ID: 0066
Revises: 0065
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_config", sa.Column("alert_slack_integration_id", UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("guard_config", "alert_slack_integration_id")
