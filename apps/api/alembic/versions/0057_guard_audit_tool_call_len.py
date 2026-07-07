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


_VIEW_SQL = """
CREATE OR REPLACE VIEW unified_activity_v AS
SELECT
    workspace_id,
    ts,
    'policy'::text                AS source,
    id::text                      AS event_id,
    user_email                    AS actor,
    tool_call                     AS action,
    decision                      AS status,
    rule_id                       AS reason,
    NULL::text                    AS message,
    hook_session_id::text         AS session_id
FROM guard_audit_events

UNION ALL

SELECT
    workspace_id,
    ts,
    'tool'::text                  AS source,
    id::text                      AS event_id,
    NULL::text                    AS actor,
    tool                          AS action,
    event_type                    AS status,
    NULL::text                    AS reason,
    message,
    session_id
FROM telemetry_events;
"""


def upgrade():
    # Must drop the view before altering the column it depends on
    op.execute("DROP VIEW IF EXISTS unified_activity_v")
    op.alter_column(
        "guard_audit_events", "tool_call",
        existing_type=sa.String(50),
        type_=sa.String(255),
        existing_nullable=True,
    )
    op.execute(_VIEW_SQL)


def downgrade():
    op.execute("DROP VIEW IF EXISTS unified_activity_v")
    op.alter_column(
        "guard_audit_events", "tool_call",
        existing_type=sa.String(255),
        type_=sa.String(50),
        existing_nullable=True,
    )
    op.execute(_VIEW_SQL)
