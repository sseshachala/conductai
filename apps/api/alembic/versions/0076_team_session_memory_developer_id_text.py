"""team_session_memory: change developer_id from UUID FK to Text (stores Clerk user_id)

Revision ID: 0076
Revises: 0075
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "0076"
down_revision = "0075"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("team_session_memory_developer_id_fkey", "team_session_memory", type_="foreignkey")
    op.alter_column(
        "team_session_memory",
        "developer_id",
        existing_type=UUID(as_uuid=True),
        type_=sa.Text(),
        existing_nullable=True,
        postgresql_using="developer_id::text",
    )


def downgrade():
    op.alter_column(
        "team_session_memory",
        "developer_id",
        existing_type=sa.Text(),
        type_=UUID(as_uuid=True),
        existing_nullable=True,
        postgresql_using="developer_id::uuid",
    )
    op.create_foreign_key(
        "team_session_memory_developer_id_fkey",
        "team_session_memory", "users",
        ["developer_id"], ["id"],
        ondelete="SET NULL",
    )
