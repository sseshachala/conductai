"""add deny_on_error to guard_config

Revision ID: 0054
Revises: 0053
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "guard_config",
        sa.Column("deny_on_error", sa.Boolean, nullable=False, server_default="true"),
    )


def downgrade():
    op.drop_column("guard_config", "deny_on_error")
