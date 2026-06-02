"""Guard: add tool_use_id to guard_audit_events for PostToolUse token tracking

Revision ID: 0052
Revises: 0051
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE guard_audit_events
        ADD COLUMN IF NOT EXISTS tool_use_id TEXT
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_guard_audit_events_tool_use_id
        ON guard_audit_events (tool_use_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_guard_audit_events_tool_use_id")
    op.execute("ALTER TABLE guard_audit_events DROP COLUMN IF EXISTS tool_use_id")
