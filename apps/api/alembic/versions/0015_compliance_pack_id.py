"""add pack_id to guard_policies and security_policies

Revision ID: 0015
Revises: 0014
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_policies", sa.Column("pack_id", sa.String(100), nullable=True))
    op.add_column("security_policies", sa.Column("pack_id", sa.String(100), nullable=True))
    op.create_index("ix_guard_policies_pack_id", "guard_policies", ["pack_id"])
    op.create_index("ix_security_policies_pack_id", "security_policies", ["pack_id"])


def downgrade() -> None:
    op.drop_index("ix_security_policies_pack_id", "security_policies")
    op.drop_index("ix_guard_policies_pack_id", "guard_policies")
    op.drop_column("security_policies", "pack_id")
    op.drop_column("guard_policies", "pack_id")
