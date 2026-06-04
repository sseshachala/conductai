"""guard: add guard_developer_tools table for per-developer AI tool coverage tracking

Revision ID: 0056
Revises: 0055
Create Date: 2026-06-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS guard_developer_tools (
            id              SERIAL PRIMARY KEY,
            workspace_id    TEXT NOT NULL,
            user_email      TEXT NOT NULL,
            detected_tools  JSONB NOT NULL DEFAULT '[]',
            mcp_registered  JSONB NOT NULL DEFAULT '[]',
            hook_registered JSONB NOT NULL DEFAULT '[]',
            reported_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_guard_dev_tools UNIQUE (workspace_id, user_email)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_guard_developer_tools_workspace_id
        ON guard_developer_tools (workspace_id)
    """)


def downgrade():
    op.execute("ALTER TABLE IF EXISTS guard_developer_tools RENAME TO guard_developer_tools_removed_0056")
