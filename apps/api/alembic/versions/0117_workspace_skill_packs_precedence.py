"""Add precedence column to workspace_skill_packs (#1737 PR 1).

Pack-level precedence resolves tie-breaks when rules from different packs match
with the same action severity. Higher value wins. Default 100 lets admins push
individual packs up or down without renumbering the whole set.

Revision ID: 0117
Revises: 0116
Create Date: 2026-09-09
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0117"
down_revision = "0116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_skill_packs",
        sa.Column(
            "precedence",
            sa.Integer(),
            nullable=False,
            server_default="100",
        ),
    )


def downgrade() -> None:
    op.drop_column("workspace_skill_packs", "precedence")
