"""users.setup_completed_at — first-time setup gate (#858 slice 1)

Revision ID: 0033
Revises: 0032
Create Date: 2026-06-26
"""

from alembic import op
import sqlalchemy as sa


revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("setup_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill: existing users have already gone through whatever onboarding
    # existed before this migration. Only brand-new signups should see /setup.
    op.execute("UPDATE users SET setup_completed_at = now() WHERE setup_completed_at IS NULL")


def downgrade() -> None:
    op.drop_column("users", "setup_completed_at")
