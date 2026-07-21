"""Seed well-known public MCP servers for all existing workspaces.

These are system-managed rows (is_system=true, no auth). Users connect
their own token via the Integrations page. Names match the server_name
field used in playbook type:mcp blocks.

Revision ID: 0082
Revises: 0081
Create Date: 2026-07-20
"""
from alembic import op
import sqlalchemy as sa

revision = "0082"
down_revision = "0081"
branch_labels = None
depends_on = None

# (name, url, transport) — name must match server_name in playbook YAML
SYSTEM_SERVERS = [
    # Hosted MCP servers with real public endpoints
    ("slack",  "https://mcp.slack.com",     "sse"),
    ("linear", "https://mcp.linear.app/mcp","http"),
    # GitHub has no universal public MCP endpoint — users add their own URL
    # (Docker: ghcr.io/github/github-mcp-server on localhost:3000)
    # REST fallback in dag_runner covers GitHub until MCP is configured
]


def upgrade() -> None:
    conn = op.get_bind()
    workspace_ids = [
        str(r.id)
        for r in conn.execute(sa.text("SELECT id FROM workspaces")).fetchall()
    ]

    for ws_id in workspace_ids:
        for name, url, transport in SYSTEM_SERVERS:
            conn.execute(sa.text("""
                INSERT INTO mcp_servers
                    (id, workspace_id, environment_id, name, url, transport, is_system, encrypted_auth, created_at)
                VALUES
                    (gen_random_uuid(), :ws, NULL, :name, :url, :transport, true, NULL, now())
                ON CONFLICT DO NOTHING
            """), {"ws": ws_id, "name": name, "url": url, "transport": transport})


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM mcp_servers WHERE is_system = true AND name = ANY(:names)"),
        {"names": [s[0] for s in SYSTEM_SERVERS]},
    )
