"""add execution_status and result_summary to guard_audit_events

Revision ID: 0081
Revises: 0080
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_audit_events", sa.Column("execution_status", sa.String(20), nullable=True))
    op.add_column("guard_audit_events", sa.Column("result_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("guard_audit_events", "result_summary")
    op.drop_column("guard_audit_events", "execution_status")
