"""recreate unified_activity_v — restore view if dropped by failed 0057 migration

Revision ID: 0058
Revises: 0057
Create Date: 2026-07-07
"""
from alembic import op

revision = "0058"
down_revision = "0057"
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
    op.execute(_VIEW_SQL)


def downgrade():
    op.execute("DROP VIEW IF EXISTS unified_activity_v")
