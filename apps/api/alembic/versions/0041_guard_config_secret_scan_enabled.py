"""guard_config: add secret_scan_enabled flag

Revision ID: 0041
Revises: 0040
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "guard_config",
        sa.Column("secret_scan_enabled", sa.Boolean(), nullable=False, server_default="true"),
    )


def downgrade():
    op.drop_column("guard_config", "secret_scan_enabled")
