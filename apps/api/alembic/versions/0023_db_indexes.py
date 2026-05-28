"""0023 db indexes — cover heavy query paths

Adds explicit indexes for the dashboard, runs, trace, and audit paths
that are currently doing sequential scans as run volume grows.

Revision ID: 0023
Revises: 0022
Create Date: 2026-05-27
"""
from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy import text
    conn = op.get_bind()
    indexes = [
        "CREATE INDEX IF NOT EXISTS ix_runs_workflow_version_id ON runs (workflow_version_id)",
        "CREATE INDEX IF NOT EXISTS ix_runs_status ON runs (status)",
        "CREATE INDEX IF NOT EXISTS ix_runs_created_at ON runs (created_at)",
        "CREATE INDEX IF NOT EXISTS ix_runs_version_created ON runs (workflow_version_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_run_events_run_id ON run_events (run_id)",
        "CREATE INDEX IF NOT EXISTS ix_run_events_run_created ON run_events (run_id, created_at)",
        "CREATE INDEX IF NOT EXISTS ix_workflows_workspace_id ON workflows (workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_workflows_project_id ON workflows (project_id)",
        "CREATE INDEX IF NOT EXISTS ix_workflow_versions_workflow_id ON workflow_versions (workflow_id)",
        "CREATE INDEX IF NOT EXISTS ix_integrations_workspace_id ON integrations (workspace_id)",
        "CREATE INDEX IF NOT EXISTS ix_integrations_workspace_environment ON integrations (workspace_id, environment_id)",
        "CREATE INDEX IF NOT EXISTS ix_audit_log_workspace_created ON audit_log (workspace_id, created_at)",
    ]
    for sql in indexes:
        conn.execute(text(sql))


def downgrade():
    from sqlalchemy import text
    conn = op.get_bind()
    for name in [
        "ix_runs_workflow_version_id", "ix_runs_status", "ix_runs_created_at",
        "ix_runs_version_created", "ix_run_events_run_id", "ix_run_events_run_created",
        "ix_workflows_workspace_id", "ix_workflows_project_id",
        "ix_workflow_versions_workflow_id", "ix_integrations_workspace_id",
        "ix_integrations_workspace_environment", "ix_audit_log_workspace_created",
    ]:
        conn.execute(text(f"DROP INDEX IF EXISTS {name}"))
