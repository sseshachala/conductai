"""guard_team_preferences

Revision ID: 0039
Revises: 0038
Create Date: 2026-05-31

"""
import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guard_teams",
        sa.Column("alert_channel", sa.String(100), nullable=True),
    )
    op.add_column(
        "guard_teams",
        sa.Column("notify_on_block", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "guard_teams",
        sa.Column("notify_on_budget", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )


def downgrade() -> None:
    op.drop_column("guard_teams", "notify_on_budget")
    op.drop_column("guard_teams", "notify_on_block")
    op.drop_column("guard_teams", "alert_channel")
