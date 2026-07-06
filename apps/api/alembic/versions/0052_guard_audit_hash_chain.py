"""add hash-chain columns to guard_audit_events

Revision ID: 0052
Revises: 0051
Create Date: 2026-07-06
"""
from alembic import op
import sqlalchemy as sa

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("guard_audit_events", sa.Column("previous_hash", sa.Text, nullable=True))
    op.add_column("guard_audit_events", sa.Column("entry_hash", sa.Text, nullable=True))
    op.create_index("ix_guard_audit_events_entry_hash", "guard_audit_events", ["entry_hash"])


def downgrade():
    op.drop_index("ix_guard_audit_events_entry_hash", table_name="guard_audit_events")
    op.drop_column("guard_audit_events", "entry_hash")
    op.drop_column("guard_audit_events", "previous_hash")
