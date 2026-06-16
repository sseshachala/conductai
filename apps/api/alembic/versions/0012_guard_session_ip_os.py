"""guard_session: add client_ip and os_info columns

Revision ID: 0012
Revises: 0011
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("guard_sessions", sa.Column("client_ip", sa.String(64), nullable=True))
    op.add_column("guard_sessions", sa.Column("os_info", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column("guard_sessions", "os_info")
    op.drop_column("guard_sessions", "client_ip")
