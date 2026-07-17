"""add context_summary to glens chat sessions

Revision ID: 0080
Revises: 0079
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("glens_chat_sessions", sa.Column("context_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("glens_chat_sessions", "context_summary")
