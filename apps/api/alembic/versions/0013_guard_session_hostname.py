"""guard_session: add hostname column

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_sessions", sa.Column("hostname", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("guard_sessions", "hostname")
