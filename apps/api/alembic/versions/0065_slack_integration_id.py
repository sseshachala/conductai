"""add slack_integration_id to security_config and guard_config

Revision ID: 0065
Revises: 0064
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0065"
down_revision = "0064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("security_config", sa.Column("slack_integration_id", UUID(as_uuid=True), nullable=True))
    op.add_column("guard_config", sa.Column("slack_integration_id", UUID(as_uuid=True), nullable=True))


def downgrade() -> None:
    op.drop_column("security_config", "slack_integration_id")
    op.drop_column("guard_config", "slack_integration_id")
