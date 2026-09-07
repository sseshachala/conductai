"""Add is_pinned column to workspace_report_layouts (#1450 PR 5).

Workspace-level flag surfaced in the left nav under a "Reports" section.
Every workspace member with view perm sees the same pinned set — pin is
not per-user (the epic locks reports as workspace-scoped resources).

Revision ID: 0115
Revises: 0114
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0115"
down_revision = "0114"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_report_layouts",
        sa.Column(
            "is_pinned", sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("workspace_report_layouts", "is_pinned")
