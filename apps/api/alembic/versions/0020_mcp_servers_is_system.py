"""Add is_system flag to mcp_servers

Revision ID: 0020
Revises: 0019
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("mcp_servers", sa.Column("is_system", sa.Boolean(), nullable=False, server_default="false"))
    op.execute("UPDATE mcp_servers SET is_system = true WHERE name = 'Conduct AI Guard'")


def downgrade() -> None:
    op.drop_column("mcp_servers", "is_system")
