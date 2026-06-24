"""Backfill encrypted_auth for auto-provisioned Conduct AI Guard MCP rows.

Before 1bca22a (2026-06-24), every workspace was provisioned with an
mcp_servers row whose URL contained `&token=<member_token>` and whose
encrypted_auth was NULL. After 1bca22a, new rows put the token in
encrypted_auth (proper {token: <value>} shape) and strip it from the URL.

This migration brings existing rows in line:
  - parse token out of URL
  - strip the `&token=...` segment from URL
  - encrypt {token: <value>} into encrypted_auth

The legacy URL form keeps working via the mcp.py fallback path even if
this migration fails to run — so this is non-breaking. The win is that
the token stops appearing in the Settings → Integrations UI and stops
landing in browser history when a user copies the URL.

Revision ID: 0030
Revises: 0029
Create Date: 2026-06-24
"""
from __future__ import annotations

import re
from alembic import op
from sqlalchemy import text

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


_TOKEN_PATTERN = re.compile(r"&token=([^&]+)")


def upgrade() -> None:
    from app.core.crypto import encrypt as _enc

    conn = op.get_bind()
    rows = conn.execute(text("""
        SELECT id, url
        FROM mcp_servers
        WHERE name = 'Conduct AI Guard'
          AND encrypted_auth IS NULL
          AND url LIKE '%&token=%'
    """)).fetchall()

    migrated = 0
    for row in rows:
        match = _TOKEN_PATTERN.search(row.url)
        if not match:
            continue
        token_value = match.group(1)
        clean_url = _TOKEN_PATTERN.sub("", row.url)
        encrypted = _enc({"token": token_value})

        conn.execute(text("""
            UPDATE mcp_servers
            SET url = :url, encrypted_auth = :auth
            WHERE id = :id
        """), {"url": clean_url, "auth": encrypted, "id": row.id})
        migrated += 1

    if migrated:
        print(f"  backfilled {migrated} Conduct AI Guard MCP rows")


def downgrade() -> None:
    # Reverse path: take encrypted_auth back into URL form. Decryption fails
    # gracefully — rows without recoverable encrypted_auth are left alone.
    from app.core.crypto import decrypt as _dec

    conn = op.get_bind()
    rows = conn.execute(text("""
        SELECT id, url, encrypted_auth
        FROM mcp_servers
        WHERE name = 'Conduct AI Guard'
          AND encrypted_auth IS NOT NULL
          AND url NOT LIKE '%&token=%'
    """)).fetchall()

    for row in rows:
        try:
            data = _dec(row.encrypted_auth)
            token_value = data.get("token")
        except Exception:
            continue
        if not token_value:
            continue
        new_url = row.url + f"&token={token_value}"
        conn.execute(text("""
            UPDATE mcp_servers
            SET url = :url, encrypted_auth = NULL
            WHERE id = :id
        """), {"url": new_url, "id": row.id})
