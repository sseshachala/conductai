"""guard_config: flip fail_mode default to fail_closed

Revision ID: 0059
Revises: 0058
Create Date: 2026-07-08
"""
from alembic import op

revision = "0059"
down_revision = "0058"
branch_labels = None
depends_on = None


def upgrade():
    # Flip ALL existing workspaces that still have the old default.
    # Anyone who deliberately chose fail_open via settings keeps it.
    # Since fail_open was the only shipped value, this flips everyone.
    op.execute(
        "UPDATE guard_config SET fail_mode = 'fail_closed' WHERE fail_mode = 'fail_open'"
    )


def downgrade():
    op.execute(
        "UPDATE guard_config SET fail_mode = 'fail_open' WHERE fail_mode = 'fail_closed'"
    )
