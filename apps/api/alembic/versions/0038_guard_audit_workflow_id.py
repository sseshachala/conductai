"""Add conductai_workflow_id to guard_audit_events for run deep-link

Revision ID: 0038_guard_audit_workflow_id
Revises: 0037_fix_no_env_commits_pattern
Create Date: 2026-06-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0038_guard_audit_workflow_id"
down_revision = "0037_fix_no_env_commits_pattern"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_audit_events", sa.Column("conductai_workflow_id", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("guard_audit_events", "conductai_workflow_id")
