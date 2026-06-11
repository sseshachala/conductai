"""add ON DELETE CASCADE to workflow FK chain

Revision ID: 0080
Revises: 0079
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0080"
down_revision = "0079"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # workflow_versions.workflow_id → workflows.id
    # Named explicitly in migration 0001 as "fk_workflow_versions_workflow_id".
    op.drop_constraint(
        "fk_workflow_versions_workflow_id",
        "workflow_versions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_workflow_versions_workflow_id",
        "workflow_versions",
        "workflows",
        ["workflow_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # runs.workflow_version_id → workflow_versions.id
    # Auto-named by PostgreSQL when created via sa.ForeignKey() in 0001.
    op.drop_constraint(
        "runs_workflow_version_id_fkey",
        "runs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "runs_workflow_version_id_fkey",
        "runs",
        "workflow_versions",
        ["workflow_version_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # run_events.run_id → runs.id
    # Auto-named by PostgreSQL when created via sa.ForeignKey() in 0001.
    op.drop_constraint(
        "run_events_run_id_fkey",
        "run_events",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "run_events_run_id_fkey",
        "run_events",
        "runs",
        ["run_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Restore run_events FK without CASCADE
    op.drop_constraint("run_events_run_id_fkey", "run_events", type_="foreignkey")
    op.create_foreign_key(
        "run_events_run_id_fkey",
        "run_events",
        "runs",
        ["run_id"],
        ["id"],
    )

    # Restore runs FK without CASCADE
    op.drop_constraint("runs_workflow_version_id_fkey", "runs", type_="foreignkey")
    op.create_foreign_key(
        "runs_workflow_version_id_fkey",
        "runs",
        "workflow_versions",
        ["workflow_version_id"],
        ["id"],
    )

    # Restore workflow_versions FK without CASCADE
    op.drop_constraint("fk_workflow_versions_workflow_id", "workflow_versions", type_="foreignkey")
    op.create_foreign_key(
        "fk_workflow_versions_workflow_id",
        "workflow_versions",
        "workflows",
        ["workflow_id"],
        ["id"],
    )
