"""Add glens_chat_feedback table — per-message thumbs up/down.

Revision ID: 0107
Revises: 0106
Create Date: 2026-08-29

One row per (session, message, user); latest verdict wins on upsert
(enforced by uq_glens_chat_feedback_session_msg_user). Feeds LLM tuning /
prompt regression signal.

Constraints/indexes named explicitly per project convention (Alembic
autogenerate is banned on this repo — hand-written names avoid drift).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0107"
down_revision = "0106"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "glens_chat_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "workspaces.id",
                ondelete="CASCADE",
                name="glens_chat_feedback_workspace_id_fkey",
            ),
            nullable=False,
        ),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey(
                "glens_chat_sessions.id",
                ondelete="CASCADE",
                name="glens_chat_feedback_session_id_fkey",
            ),
            nullable=False,
        ),
        sa.Column("message_id", sa.String(length=64), nullable=False),
        sa.Column("verdict", sa.String(length=4), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("clerk_user_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "session_id", "message_id", "clerk_user_id",
            name="uq_glens_chat_feedback_session_msg_user",
        ),
        sa.CheckConstraint(
            "verdict IN ('up', 'down')",
            name="ck_glens_chat_feedback_verdict",
        ),
    )
    op.create_index(
        "ix_glens_chat_feedback_workspace_created",
        "glens_chat_feedback",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_glens_chat_feedback_workspace_created", table_name="glens_chat_feedback")
    op.drop_table("glens_chat_feedback")
