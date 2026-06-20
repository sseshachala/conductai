"""Fix Conduct AI Guard MCP transport: sse → http (Guard endpoint is JSON-RPC over HTTP)

Revision ID: 0021
Revises: 0020
Create Date: 2026-06-20
"""
from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE mcp_servers SET transport = 'http' WHERE name = 'Conduct AI Guard'")


def downgrade() -> None:
    op.execute("UPDATE mcp_servers SET transport = 'sse' WHERE name = 'Conduct AI Guard'")
