"""guard_audit_events: add hash_version (audit chain v2, #2421)

Existing rows are v1 (hash over ts|tool_call|decision|previous_hash) and are
never rehashed; new rows are written as v2 (hash over the full record). A
constant server default keeps the ADD COLUMN metadata-only on PostgreSQL 11+.

Revision ID: 0170
Revises: 0169
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0170"
down_revision = "0169"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "guard_audit_events",
        sa.Column("hash_version", sa.SmallInteger(), nullable=False, server_default=sa.text("1")),
    )


def downgrade():
    op.drop_column("guard_audit_events", "hash_version")
