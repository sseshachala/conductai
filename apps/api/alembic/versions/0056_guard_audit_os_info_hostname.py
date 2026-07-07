"""guard_audit_events: add os_info and hostname columns

Revision ID: 0056
Revises: 0055
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa

revision = "0056"
down_revision = "0055"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("guard_audit_events", sa.Column("os_info", sa.String(128), nullable=True))
    op.add_column("guard_audit_events", sa.Column("hostname", sa.String(255), nullable=True))


def downgrade():
    op.drop_column("guard_audit_events", "hostname")
    op.drop_column("guard_audit_events", "os_info")
