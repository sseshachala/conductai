"""add allowed_hosts to environments for egress allowlist (#206)

Revision ID: 0019
Revises: 0018
Create Date: 2026-05-25

Nullable JSONB column — null means unrestricted (today's default).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("environments", sa.Column("allowed_hosts", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("environments", "allowed_hosts")
