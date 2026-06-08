"""add autopilot_enabled to security_config

Revision ID: 0069
Revises: 0068
Create Date: 2026-06-08
"""
from alembic import op
import sqlalchemy as sa

revision = "0069"
down_revision = "0068"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "security_config",
        sa.Column("autopilot_enabled", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("security_config", "autopilot_enabled")
