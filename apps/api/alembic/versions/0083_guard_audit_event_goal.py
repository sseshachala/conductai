"""Add goal_id and goal_name to guard_audit_events.

Revision ID: 0083
Revises: 0082
Create Date: 2026-07-17
"""
from alembic import op
import sqlalchemy as sa

revision = "0083"
down_revision = "0082"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_audit_events", sa.Column("goal_id", sa.String(255), nullable=True))
    op.add_column("guard_audit_events", sa.Column("goal_name", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("guard_audit_events", "goal_name")
    op.drop_column("guard_audit_events", "goal_id")
