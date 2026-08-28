"""feat(#1347): workspace_llm_primitives table

One row per workspace, holds preferred_provider + tier_map for LLM routing.
API keys stay in Vault; this is config-only. See issue #1347 for design.

No consumer wiring yet — PRs B/C/D follow.

Revision ID: 0103
Revises: 0102
Create Date: 2026-08-28
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0103"
down_revision = "0102"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_llm_primitives",
        sa.Column(
            "workspace_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("preferred_provider", sa.String(length=50), nullable=False, server_default="anthropic"),
        sa.Column("tier_map", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("workspace_llm_primitives")
