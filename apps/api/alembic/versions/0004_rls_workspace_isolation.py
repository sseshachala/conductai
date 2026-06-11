"""Add Row-Level Security workspace isolation to 5 tables.

Each table gets:
  ENABLE ROW LEVEL SECURITY (non-owners subject to policy)
  CREATE POLICY tenant_isolation ... USING (workspace_id = current_setting('app.current_workspace', true)::uuid)

Tables: workflows, audit_log, watchdog_events, security_findings, conduct_api_keys

NOT applied to runs — the background worker queries runs across all workspaces.
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_TABLES = [
    "workflows",
    "audit_log",
    "watchdog_events",
    "security_findings",
    "conduct_api_keys",
]

_POLICY_SQL = """
CREATE POLICY tenant_isolation ON {table}
  AS PERMISSIVE FOR SELECT
  USING (workspace_id = current_setting('app.current_workspace', true)::uuid)
"""


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(_POLICY_SQL.format(table=table))


def downgrade() -> None:
    for table in _TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
