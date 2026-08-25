"""chore(glens): drop dead glens_enabled workspace_config rows

GLens install/uninstall endpoints were removed when GLens became a
first-class product (nav link + Cmd+K) rather than an optional module.
The `workspace_config` rows keyed `glens_enabled` are now orphaned —
nothing reads or writes them. Delete them.

Revision ID: 0098
Revises: 0097
Create Date: 2026-08-25
"""
from __future__ import annotations

from alembic import op

revision = "0098"
down_revision = "0097"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM workspace_config WHERE key = 'glens_enabled'")


def downgrade() -> None:
    # Data-only cleanup — nothing meaningful to restore.
    pass
