"""feat(guard): add security_emit_enabled, security_slack_alerts_enabled, security_slack_channel to guard_config

Revision ID: 0062
Revises: 0061
Create Date: 2026-06-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_config", sa.Column("security_emit_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("guard_config", sa.Column("security_slack_alerts_enabled", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("guard_config", sa.Column("security_slack_channel", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("guard_config", "security_slack_channel")
    op.drop_column("guard_config", "security_slack_alerts_enabled")
    op.drop_column("guard_config", "security_emit_enabled")
