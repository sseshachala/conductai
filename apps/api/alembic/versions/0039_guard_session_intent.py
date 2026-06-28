"""Add intent, tool_sequence, session_parse_status, session_parser to guard_sessions

Revision ID: 0039_guard_session_intent
Revises: 0038_guard_audit_workflow_id
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0039_guard_session_intent"
down_revision = "0038_guard_audit_workflow_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_sessions", sa.Column("intent", sa.Text(), nullable=True))
    op.add_column("guard_sessions", sa.Column("tool_sequence", JSONB(), nullable=True))
    op.add_column("guard_sessions", sa.Column("session_parse_status", sa.String(20), nullable=True))
    op.add_column("guard_sessions", sa.Column("session_parser", sa.String(30), nullable=True))


def downgrade() -> None:
    op.drop_column("guard_sessions", "session_parser")
    op.drop_column("guard_sessions", "session_parse_status")
    op.drop_column("guard_sessions", "tool_sequence")
    op.drop_column("guard_sessions", "intent")
