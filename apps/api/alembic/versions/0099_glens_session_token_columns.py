"""feat(lens): session-scoped tokens for Guard-enforced Lens (#1218 Step 3b)

Extends glens_chat_sessions with two columns:

  token_hash        SHA-256 of the raw cond_lens_* token minted at session
                    start. Raw token never persisted; only its hash.
  token_revoked_at  Ops kill-switch — set NOW() to disable the session's
                    Lens access without disturbing the workspace or other
                    sessions.

Session IS the token holder — one source of truth, no join, no new table.
Mirrors the cond_run_* pattern used by workflows. Blast radius: one chat
session (~50 turns × ~24h idle).

Revision ID: 0099
Revises: 0098
Create Date: 2026-08-25
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0099"
down_revision = "0098"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "glens_chat_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "glens_chat_sessions",
        sa.Column("token_revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Index for token lookups on the auth-check hot path.
    op.create_index(
        "ix_glens_chat_sessions_token_hash",
        "glens_chat_sessions",
        ["token_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_glens_chat_sessions_token_hash", table_name="glens_chat_sessions")
    op.drop_column("glens_chat_sessions", "token_revoked_at")
    op.drop_column("glens_chat_sessions", "token_hash")
