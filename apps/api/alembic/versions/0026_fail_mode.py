"""fail_mode — opt-in fail-closed behavior on Guard outage

Adds `fail_mode` to guard_config. Default is fail_open: when the CLI hook
cannot reach the Guard API or has no cached policy, tool calls proceed.
fail_closed flips that to block-with-rule_id='guard-unavailable'.

Resolves #763.

Revision ID: 0026
Revises: 0025
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guard_config",
        sa.Column(
            "fail_mode",
            sa.String(20),
            nullable=False,
            server_default="fail_open",
        ),
    )


def downgrade() -> None:
    op.drop_column("guard_config", "fail_mode")
