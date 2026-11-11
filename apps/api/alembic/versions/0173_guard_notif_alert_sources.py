"""guard_notification_channels: source/event columns for unified alerts (#2142, #2524).

Adds source_type (default 'guard' so every existing row keeps meaning),
source_id, event_type and threshold_per_min, and widens the action CHECK to
allow 'alert' (the action value used by every non-guard source). Existing Guard
rows are untouched.

NOTE: other branches add migrations in parallel; renumber/rebase down_revision
if 0173 is already taken on main.

Revision ID: 0173
Revises: 0172
Create Date: 2026-11-11
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0173"
down_revision = "0172"
branch_labels = None
depends_on = None

_TBL = "guard_notification_channels"


def upgrade() -> None:
    op.add_column(_TBL, sa.Column("source_type", sa.String(32), nullable=False, server_default="guard"))
    op.add_column(_TBL, sa.Column("source_id", sa.String(64), nullable=True))
    op.add_column(_TBL, sa.Column("event_type", sa.String(48), nullable=True))
    op.add_column(_TBL, sa.Column("threshold_per_min", sa.Integer(), nullable=True))

    op.drop_constraint("ck_guard_notif_channel_action", _TBL, type_="check")
    op.create_check_constraint(
        "ck_guard_notif_channel_action", _TBL,
        "action IN ('block', 'warn', 'audit', 'approval', 'fail_open', 'drift', 'alert')",
    )
    op.create_check_constraint(
        "ck_guard_notif_channel_source_event", _TBL,
        "(source_type = 'guard' AND event_type IS NULL) "
        "OR (source_type <> 'guard' AND event_type IS NOT NULL AND action = 'alert')",
    )
    op.create_index(
        "idx_guard_notif_workspace_source_event", _TBL,
        ["workspace_id", "source_type", "event_type"],
    )


def downgrade() -> None:
    op.drop_index("idx_guard_notif_workspace_source_event", table_name=_TBL)
    op.drop_constraint("ck_guard_notif_channel_source_event", _TBL, type_="check")
    op.execute("DELETE FROM guard_notification_channels WHERE action = 'alert'")
    op.drop_constraint("ck_guard_notif_channel_action", _TBL, type_="check")
    op.create_check_constraint(
        "ck_guard_notif_channel_action", _TBL,
        "action IN ('block', 'warn', 'audit', 'approval', 'fail_open', 'drift')",
    )
    op.drop_column(_TBL, "threshold_per_min")
    op.drop_column(_TBL, "event_type")
    op.drop_column(_TBL, "source_id")
    op.drop_column(_TBL, "source_type")
