"""add advisory_mode to guard_config

Revision ID: 0055
Revises: 0054
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "guard_config",
        sa.Column("advisory_mode", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade():
    op.drop_column("guard_config", "advisory_mode")
