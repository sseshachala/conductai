"""workflow_guard_settings — per-workflow Guard on/off + persona override

Moves Guard config from per-run modal to per-workflow Settings tab.

  guard_enabled    bool default true  — toggle Guard for this workflow
  runtime_persona  text nullable      — override workspace persona (NULL = inherit)

Per-run override remains supported on the API (body.guard_enabled) for
programmatic callers, but the UI Run modal no longer exposes the toggle —
Settings is the single place to configure.

Revision ID: 0029
Revises: 0028
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflows",
        sa.Column("guard_enabled", sa.Boolean, nullable=False, server_default="true"),
    )
    op.add_column(
        "workflows",
        sa.Column("runtime_persona", sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workflows", "runtime_persona")
    op.drop_column("workflows", "guard_enabled")
