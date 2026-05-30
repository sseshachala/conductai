"""add resolved_at to watchdog_events

Revision ID: 0032
Revises: 0031
"""
from alembic import op
import sqlalchemy as sa

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "watchdog_events",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("watchdog_events", "resolved_at")
