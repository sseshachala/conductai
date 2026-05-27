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
        ("ix_runs_workflow_version_id",          "CREATE INDEX IF NOT EXISTS ix_runs_workflow_version_id ON runs (workflow_version_id)"),
        ("ix_runs_status",                        "CREATE INDEX IF NOT EXISTS ix_runs_status ON runs (status)"),
        ("ix_runs_created_at",                    "CREATE INDEX IF NOT EXISTS ix_runs_created_at ON runs (created_at)"),
        ("ix_runs_version_created",               "CREATE INDEX IF NOT EXISTS ix_runs_version_created ON runs (workflow_version_id, created_at)"),
        ("ix_run_events_run_id",                  "CREATE INDEX IF NOT EXISTS ix_run_events_run_id ON run_events (run_id)"),
        ("ix_run_events_run_created",             "CREATE INDEX IF NOT EXISTS ix_run_events_run_created ON run_events (run_id, created_at)"),
        ("ix_workflows_workspace_id",             "CREATE INDEX IF NOT EXISTS ix_workflows_workspace_id ON workflows (workspace_id)"),
        ("ix_workflows_project_id",               "CREATE INDEX IF NOT EXISTS ix_workflows_project_id ON workflows (project_id)"),
        ("ix_workflow_versions_workflow_id",      "CREATE INDEX IF NOT EXISTS ix_workflow_versions_workflow_id ON workflow_versions (workflow_id)"),
        ("ix_integrations_workspace_id",          "CREATE INDEX IF NOT EXISTS ix_integrations_workspace_id ON integrations (workspace_id)"),
        ("ix_integrations_workspace_environment", "CREATE INDEX IF NOT EXISTS ix_integrations_workspace_environment ON integrations (workspace_id, environment_id)"),
        ("ix_audit_log_workspace_created",        "CREATE INDEX IF NOT EXISTS ix_audit_log_workspace_created ON audit_log (workspace_id, created_at)"),
    ]
    for _, sql in indexes:
        conn.execute(text(sql))


def downgrade():
    op.drop_index("ix_runs_workflow_version_id",        table_name="runs")
    op.drop_index("ix_runs_status",                     table_name="runs")
    op.drop_index("ix_runs_created_at",                 table_name="runs")
    op.drop_index("ix_runs_version_created",            table_name="runs")
    op.drop_index("ix_run_events_run_id",               table_name="run_events")
    op.drop_index("ix_run_events_run_created",          table_name="run_events")
    op.drop_index("ix_workflows_workspace_id",          table_name="workflows")
    op.drop_index("ix_workflows_project_id",            table_name="workflows")
    op.drop_index("ix_workflow_versions_workflow_id",   table_name="workflow_versions")
    op.drop_index("ix_integrations_workspace_id",       table_name="integrations")
    op.drop_index("ix_integrations_workspace_environment", table_name="integrations")
    op.drop_index("ix_audit_log_workspace_created",     table_name="audit_log")
