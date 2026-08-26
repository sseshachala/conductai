"""chore(lens): drop render_spec orphan column on glens_chat_sessions

Added in migration 0076 alongside the initial glens_chat_sessions schema,
but never populated or read anywhere in the codebase. Confirmed by grep:
only reference sites are the model column definition and this table's
original CREATE. No writer, no reader.

Dropping now as the tail-end cleanup of #1218. If a dashboard-spec feature
ever needs a similar column, prefer JSON-typed and populated from day one.

Revision ID: 0100
Revises: 0099
Create Date: 2026-08-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("glens_chat_sessions", "render_spec")


def downgrade() -> None:
    op.add_column(
        "glens_chat_sessions",
        sa.Column("render_spec", sa.Text(), nullable=True),
    )
