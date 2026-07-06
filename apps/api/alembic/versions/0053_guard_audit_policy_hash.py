"""add policy_hash to guard_audit_events

Revision ID: 0053
Revises: 0052
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("guard_audit_events", sa.Column("policy_hash", sa.Text, nullable=True))


def downgrade():
    op.drop_column("guard_audit_events", "policy_hash")
