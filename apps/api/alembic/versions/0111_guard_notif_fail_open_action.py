"""Widen guard_notification_channels.action CHECK to allow 'fail_open' (#1520 PR 3).

Migration 0092 seeded the check with the four action tiers Guard had at
the time: block / warn / audit / approval. #1520 PR 3 adds a fifth tier —
fail_open — so customers can route the fail-open WARNING to a channel of
their choice via the same UI they already use for the other tiers.

Postgres does not support ALTER CHECK CONSTRAINT in place; drop + recreate
under the same name.

Revision ID: 0111
Revises: 0110
Create Date: 2026-09-02
"""
from __future__ import annotations

from alembic import op


revision = "0111"
down_revision = "0110"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_guard_notif_channel_action",
        "guard_notification_channels",
        type_="check",
    )
    op.create_check_constraint(
        "ck_guard_notif_channel_action",
        "guard_notification_channels",
        "action IN ('block', 'warn', 'audit', 'approval', 'fail_open')",
    )


def downgrade() -> None:
    # Downgrade path: remove any fail_open rows first so the narrower
    # constraint can be re-applied without violating existing data.
    op.execute("DELETE FROM guard_notification_channels WHERE action = 'fail_open'")
    op.drop_constraint(
        "ck_guard_notif_channel_action",
        "guard_notification_channels",
        type_="check",
    )
    op.create_check_constraint(
        "ck_guard_notif_channel_action",
        "guard_notification_channels",
        "action IN ('block', 'warn', 'audit', 'approval')",
    )
