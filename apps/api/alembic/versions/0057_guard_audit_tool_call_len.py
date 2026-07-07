"""guard_audit_events: widen tool_call from String(50) to String(255)

MCP tool names like mcp__codex_apps__workspace_agents__list_available_apps
exceed the old 50-char limit and cause 500s on event ingest.

Revision ID: 0057
Revises: 0056
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0057"
down_revision = "0056"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "guard_audit_events", "tool_call",
        existing_type=sa.String(50),
        type_=sa.String(255),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "guard_audit_events", "tool_call",
        existing_type=sa.String(255),
        type_=sa.String(50),
        existing_nullable=True,
    )
