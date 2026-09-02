"""Add guard_config.notify_on_fail_open (#1520 PR 2).

Customer opt-out for the WARNING Slack post that fires when Guard falls
open. Default TRUE — transparency is the default; workspaces that find the
alerts too noisy can turn them off in Settings.

Companion to the Prometheus counter + internal ops alert that shipped in
#1570.

Revision ID: 0110
Revises: 0109 (#1565)
Create Date: 2026-09-02
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0110"
down_revision = "0109"  # #1565 (approvals latency BIGINT) must land first
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guard_config",
        sa.Column(
            "notify_on_fail_open",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("guard_config", "notify_on_fail_open")
