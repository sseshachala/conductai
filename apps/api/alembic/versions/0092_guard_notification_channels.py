"""Guard notification channels — per-action routing (#1142 Phase 1).

Introduces `guard_notification_channels` — one row per (workspace, action, channel).
Backs the per-action-tier notification UI on /theguard/settings > Notifications.

Legacy `guard_config.alert_channel` + `notify_on_block` stay in place; the API
auto-seeds the new table from those values on first read for backward compat.
Phase 3 adds pack- and rule-level overrides on top of this workspace-level table.

Revision ID: 0092
Revises: 0091
Create Date: 2026-08-14
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "0092"
down_revision = "0091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guard_notification_channels",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # action tier: block | warn | audit | approval
        sa.Column("action", sa.String(20), nullable=False),
        # channel type: slack (Phase 1). email/pagerduty/webhook land in Phase 2.
        sa.Column("channel_type", sa.String(20), nullable=False, server_default="slack"),
        # For Slack: integration_id points to a row in `integrations` (Slack bot token).
        sa.Column("integration_id", UUID(as_uuid=True), nullable=True),
        # For Slack: channel name like "#compliance-hipaa" (without the #).
        sa.Column("channel_ref", sa.String(200), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("dedupe_window_sec", sa.Integer, nullable=False, server_default=sa.text("300")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "action IN ('block', 'warn', 'audit', 'approval')",
            name="ck_guard_notif_channel_action",
        ),
        sa.CheckConstraint(
            "channel_type IN ('slack', 'email', 'pagerduty', 'webhook')",
            name="ck_guard_notif_channel_type",
        ),
    )
    op.create_index(
        "idx_guard_notif_workspace_action",
        "guard_notification_channels",
        ["workspace_id", "action"],
    )
    op.create_index(
        "idx_guard_notif_workspace_enabled",
        "guard_notification_channels",
        ["workspace_id", "enabled"],
    )


def downgrade() -> None:
    op.drop_index("idx_guard_notif_workspace_enabled", table_name="guard_notification_channels")
    op.drop_index("idx_guard_notif_workspace_action", table_name="guard_notification_channels")
    op.drop_table("guard_notification_channels")
