"""GLens chat session — link to session-scoped agent identity.

#1252 follow-up. Each new GlensChatSession mints an AgentIdentity row so
Lens LLM egress carries a real `agent_identity_id` through PolicyContext
(activates SpendCap + ThroughputCap sources for Lens usage) and audit rows
attribute cleanly with a `token_prefix`.

Column is nullable — pre-existing sessions keep the old `system:lens`
attribution until they mint on the next turn (backfill deferred).

Revision ID: 0090
Revises: 0089
Create Date: 2026-08-27
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0101"
down_revision = "0100"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "glens_chat_sessions",
        sa.Column("agent_identity_id", sa.String(length=36), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("glens_chat_sessions", "agent_identity_id")
