"""Workspace report layouts table (#1450 PR 1).

Backing store for the report-builder Lens skill. One row per (workspace,
slug); every workspace member with view perm sees every row (shared by
default, not per-user). `layout_spec` is an ordered JSONB list of
`{tool_name, hint}` widget entries; the frontend maps `hint` to a render
cell size.

Templates ("Operations" / "Observability") live in code, not here — a
"use template" click writes a new row copied from the template.

Revision ID: 0114
Revises: 0113
Create Date: 2026-09-06
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "0114"
down_revision = "0113"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_report_layouts",
        sa.Column(
            "id", UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id", UUID(as_uuid=True),
            sa.ForeignKey(
                "workspaces.id",
                name="fk_workspace_report_layouts_workspace_id",
                ondelete="CASCADE",
            ),
            nullable=False,
        ),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column(
            "layout_spec", JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.UniqueConstraint(
            "workspace_id", "slug",
            name="uq_workspace_report_layouts_ws_slug",
        ),
    )
    op.create_index(
        "ix_workspace_report_layouts_workspace_id",
        "workspace_report_layouts",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_report_layouts_workspace_id",
        table_name="workspace_report_layouts",
    )
    op.drop_table("workspace_report_layouts")
