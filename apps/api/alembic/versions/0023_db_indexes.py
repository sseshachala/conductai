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
    # ── runs ─────────────────────────────────────────────────────────────────
    # Dashboard: filter by workspace (via version→workflow→workspace) + status + date
    op.create_index("ix_runs_workflow_version_id",  "runs", ["workflow_version_id"])
    op.create_index("ix_runs_status",               "runs", ["status"])
    op.create_index("ix_runs_created_at",           "runs", ["created_at"])
    # Compound: most dashboard/runs-page queries filter version + created_at
    op.create_index("ix_runs_version_created",      "runs", ["workflow_version_id", "created_at"])

    # ── run_events ────────────────────────────────────────────────────────────
    # Trace page fetches all events for a run ordered by created_at
    op.create_index("ix_run_events_run_id",         "run_events", ["run_id"])
    op.create_index("ix_run_events_run_created",    "run_events", ["run_id", "created_at"])

    # ── workflows ─────────────────────────────────────────────────────────────
    # Agents list: filter by workspace_id; project page: filter by project_id
    op.create_index("ix_workflows_workspace_id",    "workflows", ["workspace_id"])
    op.create_index("ix_workflows_project_id",      "workflows", ["project_id"])

    # ── workflow_versions ─────────────────────────────────────────────────────
    # Run executor and dashboard join versions → workflow
    op.create_index("ix_workflow_versions_workflow_id", "workflow_versions", ["workflow_id"])

    # ── integrations ──────────────────────────────────────────────────────────
    # Credential resolution at runtime: workspace_id + environment_id
    op.create_index("ix_integrations_workspace_id",         "integrations", ["workspace_id"])
    op.create_index("ix_integrations_workspace_environment", "integrations", ["workspace_id", "environment_id"])

    # ── audit_log ─────────────────────────────────────────────────────────────
    # Audit log page: filter by workspace_id ordered by created_at desc
    op.create_index("ix_audit_log_workspace_created", "audit_log", ["workspace_id", "created_at"])


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
