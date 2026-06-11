"""Add workspace_id to runs, denormalized from workflow_versions → workflows.

Backfill: UPDATE runs SET workspace_id = w.workspace_id
          FROM workflow_versions wv JOIN workflows w ON w.id = wv.workflow_id
          WHERE runs.workflow_version_id = wv.id

Indexes added:
  ix_runs_workspace_id          (workspace_id)
  ix_runs_workspace_created     (workspace_id, created_at DESC)
  ix_runs_workspace_status      (workspace_id, status)
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add column as nullable first so the backfill can populate it
    op.add_column(
        "runs",
        sa.Column("workspace_id", UUID(as_uuid=True), nullable=True),
    )

    # 2. Backfill from workflow_versions → workflows
    op.execute(
        """
        UPDATE runs
        SET workspace_id = w.workspace_id
        FROM workflow_versions wv
        JOIN workflows w ON w.id = wv.workflow_id
        WHERE runs.workflow_version_id = wv.id
        """
    )

    # 3. Now enforce NOT NULL — all rows should have a value after backfill
    op.alter_column("runs", "workspace_id", nullable=False)

    # 4. Create indexes for common workspace-scoped access patterns
    op.create_index("ix_runs_workspace_id", "runs", ["workspace_id"])
    op.create_index(
        "ix_runs_workspace_created",
        "runs",
        ["workspace_id", sa.text("created_at DESC")],
    )
    op.create_index("ix_runs_workspace_status", "runs", ["workspace_id", "status"])


def downgrade() -> None:
    # Dropping the column cascades the indexes automatically in PostgreSQL
    op.drop_column("runs", "workspace_id")
