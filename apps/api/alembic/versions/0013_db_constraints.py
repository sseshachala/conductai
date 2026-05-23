"""add missing DB-level constraints (closes #183)

Revision ID: 0013
Revises: 0012
Create Date: 2026-05-23
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. UNIQUE (workspace_id, handle) on integrations — prevents duplicate rows
    #    from concurrent upserts racing past the app-layer check.
    op.create_unique_constraint(
        "uq_integrations_workspace_handle",
        "integrations",
        ["workspace_id", "handle"],
    )

    # 2. CHECK constraint on runs.status — valid values only.
    op.create_check_constraint(
        "ck_runs_status",
        "runs",
        "status IN ('pending', 'running', 'paused', 'succeeded', 'failed', 'cancelled')",
    )

    # 3. CHECK constraint on workspace_users.role — valid values only.
    op.create_check_constraint(
        "ck_workspace_users_role",
        "workspace_users",
        "role IN ('admin', 'editor', 'viewer')",
    )

    # 4. ON DELETE SET NULL on workflows.current_version_id — deleting a
    #    WorkflowVersion should null the pointer rather than cascade-delete
    #    the workflow or error.
    #
    #    PostgreSQL requires dropping and recreating the FK to change its
    #    ON DELETE behaviour.
    op.drop_constraint(
        "workflows_current_version_id_fkey",
        "workflows",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "workflows_current_version_id_fkey",
        "workflows",
        "workflow_versions",
        ["current_version_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Restore original FK without ON DELETE SET NULL
    op.drop_constraint("workflows_current_version_id_fkey", "workflows", type_="foreignkey")
    op.create_foreign_key(
        "workflows_current_version_id_fkey",
        "workflows",
        "workflow_versions",
        ["current_version_id"],
        ["id"],
    )

    op.drop_constraint("ck_workspace_users_role", "workspace_users", type_="check")
    op.drop_constraint("ck_runs_status", "runs", type_="check")
    op.drop_constraint("uq_integrations_workspace_handle", "integrations", type_="unique")
