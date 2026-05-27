"""0024 run leasing — attempt tracking and worker lock columns

Adds leasing/idempotency columns to runs so the queue can safely retry
failed or stale runs without double-execution.

New columns:
  attempt_count  — incremented each time a worker picks up this run
  locked_at      — timestamp when a worker claimed the run
  locked_by      — worker identity (hostname/pid) holding the lease
  next_retry_at  — earliest time the run can be retried after failure

NULL on all existing rows — executor sets these on dequeue.

Revision ID: 0024
Revises: 0023
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("runs", sa.Column("attempt_count", sa.Integer, nullable=False, server_default="0"))
    op.add_column("runs", sa.Column("locked_at",     sa.DateTime(timezone=True), nullable=True))
    op.add_column("runs", sa.Column("locked_by",     sa.String(255), nullable=True))
    op.add_column("runs", sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True))

    # Index for the queue worker: find pending runs that are ready to pick up
    op.create_index(
        "ix_runs_queue_pickup",
        "runs",
        ["status", "next_retry_at"],
        postgresql_where=sa.text("status IN ('pending', 'failed')"),
    )


def downgrade():
    op.drop_index("ix_runs_queue_pickup", table_name="runs")
    op.drop_column("runs", "next_retry_at")
    op.drop_column("runs", "locked_by")
    op.drop_column("runs", "locked_at")
    op.drop_column("runs", "attempt_count")
