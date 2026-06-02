"""Guard: add hook_session_id (plain text) for PostToolUse token correlation

Revision ID: 0053
Revises: 0052
Create Date: 2026-06-02
"""
from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE guard_audit_events
        ADD COLUMN IF NOT EXISTS hook_session_id TEXT
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_guard_audit_events_hook_session_id
        ON guard_audit_events (hook_session_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_guard_audit_events_hook_session_id")
    op.execute("ALTER TABLE guard_audit_events DROP COLUMN IF EXISTS hook_session_id")
