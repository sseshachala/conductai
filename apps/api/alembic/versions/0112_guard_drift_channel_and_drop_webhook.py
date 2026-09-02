"""Add 'drift' action tier + drop dead slack_webhook_url column (#1574).

Two changes in one migration since they're the same story: consolidating
Slack alert routing on the modern per-action fanout table
(``guard_notification_channels``) and retiring the legacy single-webhook
column.

1. Widen ``ck_guard_notif_channel_action`` to include ``drift`` — enables
   the drift alerter in savings.py to route via ``resolve_channels(...,
   "drift")`` instead of the legacy ``config.alert_channel`` path.

2. Drop ``guard_config.slack_webhook_url`` — the column was written via
   PATCH but no code path ever read it (``_post_slack_drift`` was the only
   consumer and it has zero call sites in the codebase). Removing it
   eliminates a persistent source of confusion between the two Slack
   configuration models.

Revision ID: 0112
Revises: 0111
Create Date: 2026-09-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0112"
down_revision = "0111"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Widen action CHECK to include 'drift'
    op.drop_constraint(
        "ck_guard_notif_channel_action",
        "guard_notification_channels",
        type_="check",
    )
    op.create_check_constraint(
        "ck_guard_notif_channel_action",
        "guard_notification_channels",
        "action IN ('block', 'warn', 'audit', 'approval', 'fail_open', 'drift')",
    )

    # 2. Drop the dead slack_webhook_url column. If any workspace happens to
    #    have a non-null value, log it once via a NOTICE so operators can
    #    see who was writing to a field that nothing read.
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM guard_config WHERE slack_webhook_url IS NOT NULL) THEN "
        "RAISE NOTICE 'Dropping guard_config.slack_webhook_url with % non-null rows (never read by any code path)', "
        "(SELECT COUNT(*) FROM guard_config WHERE slack_webhook_url IS NOT NULL); "
        "END IF; END $$;"
    )
    op.drop_column("guard_config", "slack_webhook_url")


def downgrade() -> None:
    # Reverse in opposite order — column first, then constraint.
    op.add_column(
        "guard_config",
        sa.Column("slack_webhook_url", sa.String(2048), nullable=True),
    )
    op.execute("DELETE FROM guard_notification_channels WHERE action = 'drift'")
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
