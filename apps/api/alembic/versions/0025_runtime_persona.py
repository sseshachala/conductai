"""runtime_persona — separate dev-time and runtime enforcement personas

Adds `runtime_persona` to guard_config. The existing `persona` column keeps
its meaning (dev-time / MCP hook / daemon sync). `runtime_persona` is read
only by the workflow runtime (guard_block.py) and defaults to 'conservative'
so production workflows enforce the strictest rule set regardless of what
the workspace's dev persona is set to.

Resolves #776.

Revision ID: 0025
Revises: 0024
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guard_config",
        sa.Column(
            "runtime_persona",
            sa.String(20),
            nullable=False,
            server_default="conservative",
        ),
    )


def downgrade() -> None:
    op.drop_column("guard_config", "runtime_persona")
