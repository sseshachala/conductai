"""add reporter_email to security_findings

Revision ID: 0067_security_finding_reporter_email
Revises: 0066_guard_alert_slack_integration_id
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0067_security_finding_reporter_email"
down_revision = "0066_guard_alert_slack_integration_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("security_findings", sa.Column("reporter_email", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("security_findings", "reporter_email")
