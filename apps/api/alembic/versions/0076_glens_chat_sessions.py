"""glens_chat_sessions table

Revision ID: 0076
Revises: 0075
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "glens_chat_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("messages", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("render_spec", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_glens_chat_sessions_workspace_id", "glens_chat_sessions", ["workspace_id"])
    op.create_index("ix_glens_chat_sessions_updated_at", "glens_chat_sessions", ["updated_at"])


def downgrade():
    op.drop_table("glens_chat_sessions")
