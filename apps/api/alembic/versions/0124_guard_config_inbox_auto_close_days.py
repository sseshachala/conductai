"""guard_config.inbox_auto_close_days — configurable per-workspace TTL for
open Guard Inbox rows that stopped re-firing.

Adds one integer column to guard_config with default 30. The Guard Inbox
worker (added in the same PR) runs a daily UPDATE that flips rows to
`status = 'resolved', resolved_reason = 'auto', resolved_by = NULL` when
`last_seen_at < NOW() - (inbox_auto_close_days || ' days')::interval`
and `inbox_auto_close_days > 0`.

Set to 0 to opt out of auto-close entirely (compliance-heavy workspaces
that must keep every open row visible until a human triages).

The trigger `guard_inbox_populate_trg` shipped in 0123 already handles
re-fire: if an auto-closed row's dedup key fires again, the trigger flips
it back to `status = 'open'` and clears the resolution metadata. No extra
handling needed for the "closed but resurfaces" case.

Revision ID: 0124
Revises: 0123
Create Date: 2026-09-12
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


# revision identifiers
revision = "0124"
down_revision = "0123"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guard_config",
        sa.Column(
            "inbox_auto_close_days",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
    )


def downgrade() -> None:
    op.drop_column("guard_config", "inbox_auto_close_days")
