"""Seed Conduct AI MCP server for all existing workspaces that have Guard configured.

Uses the first active member_token from guard_member_config per workspace.
New workspaces are seeded at creation time in the workspace creation flow.

Revision ID: 0019
Revises: 0018
Create Date: 2026-06-19
"""
from alembic import op
import sqlalchemy as sa

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

MCP_BASE = "https://api.conductai.ai/guard/mcp"


def upgrade() -> None:
    conn = op.get_bind()
    # One row per workspace — pick earliest active member token
    rows = conn.execute(sa.text("""
        SELECT DISTINCT ON (gmc.workspace_id)
            gmc.workspace_id,
            gmc.member_token
        FROM guard_member_config gmc
        WHERE gmc.active = true
        ORDER BY gmc.workspace_id, gmc.joined_at ASC
    """)).fetchall()

    for row in rows:
        ws_id = str(row.workspace_id)
        url = f"{MCP_BASE}?workspace_id={ws_id}&token={row.member_token}"
        conn.execute(sa.text("""
            INSERT INTO mcp_servers (id, workspace_id, environment_id, name, url, transport, created_at)
            VALUES (gen_random_uuid(), :ws, NULL, 'Conduct AI Guard', :url, 'sse', now())
            ON CONFLICT DO NOTHING
        """), {"ws": ws_id, "url": url})


def downgrade() -> None:
    op.execute("DELETE FROM mcp_servers WHERE name = 'Conduct AI Guard'")
