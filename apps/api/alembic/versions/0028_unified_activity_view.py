"""unified_activity_v — single view over guard_audit_events + telemetry_events

The view is the read path behind `GET /guard/events/unified`. Each underlying
table keeps its own schema and write semantics; the view exists only so the
UI can render one feed with a Source filter pill (policy / tool).

Columns are normalized to a common shape — anything per-source-specific lives
in the source tables and can be joined back via (id) when drilled in.

Run-event arm is intentionally NOT included: run_events has no workspace_id
column and would require a JOIN against `runs`. Add it in a follow-up when
there's product demand for runs interleaved with policy/tool in the feed.

Part of #718 Phase 1B.

Revision ID: 0028
Revises: 0027
Create Date: 2026-06-23
"""
from alembic import op


revision = "0028"
down_revision = "0027"
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


def upgrade() -> None:
    op.execute(_VIEW_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS unified_activity_v")
