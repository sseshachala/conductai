"""Retire /guard/mcp — migrate existing mcp_servers.url to /mcp (#1230 Phase 5).

Every mcp_servers row pointing at .../guard/mcp[?workspace_id=...] is
rewritten to .../mcp with the same query string preserved. Idempotent via
LIKE guard — safe to re-run.

New agent installs already use /mcp after the paired code changes to
apps/api/app/routers/projects.py (line 352). This migration heals the DB
so existing workspaces don't need to reinstall to migrate off the legacy
URL. /guard/mcp router remains live to handle any external client that
hasn't upgraded yet; deletion happens in a follow-up PR once traffic
drops to zero.

Revision ID: 0119
Revises: 0118
Create Date: 2026-09-09
"""
from __future__ import annotations

from alembic import op


revision = "0119"
down_revision = "0118"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE mcp_servers
        SET url = REPLACE(url, '/guard/mcp', '/mcp')
        WHERE url LIKE '%/guard/mcp%'
        """
    )


def downgrade() -> None:
    # Reversible: swap /mcp → /guard/mcp for rows that currently end in /mcp
    # via the same endpoint host. We can't distinguish rows that were always
    # /mcp from rows that were migrated by this revision, so this downgrade
    # is best-effort against the conductai.ai host only.
    op.execute(
        """
        UPDATE mcp_servers
        SET url = REPLACE(url, 'conductai.ai/mcp', 'conductai.ai/guard/mcp')
        WHERE url LIKE '%conductai.ai/mcp%'
        """
    )
