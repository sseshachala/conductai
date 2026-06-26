"""Seed real provider keys into a workspace's `env_vars` integration so the
Guard proxy can resolve them during the smoke test.

Usage — picks up any of these env vars, seeds whichever are set:
  WORKSPACE_ID=<uuid> \
  REAL_ANTHROPIC_KEY=sk-ant-… \
  REAL_OPENAI_KEY=sk-… \
  REAL_PERPLEXITY_KEY=pplx-… \
    .venv/bin/python scripts/seed_anthropic_key.py

Idempotent — merges into whatever credentials already exist on the env_vars
integration. Re-runnable; only the keys you pass get touched.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

import psycopg2

from app.core.crypto import encrypt, decrypt


DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://marshal:marshal@localhost:5432/marshal"
)
WS_ID = os.environ.get("WORKSPACE_ID")
if not WS_ID:
    sys.exit("WORKSPACE_ID required (uuid)")

# Map env var → vault key name (matches what the proxy looks up)
SOURCES = {
    "REAL_ANTHROPIC_KEY":   "ANTHROPIC_API_KEY",
    "ANTHROPIC_API_KEY":    "ANTHROPIC_API_KEY",
    "REAL_OPENAI_KEY":      "OPENAI_API_KEY",
    "OPENAI_API_KEY":       "OPENAI_API_KEY",
    "REAL_PERPLEXITY_KEY":  "PERPLEXITY_API_KEY",
    "PERPLEXITY_API_KEY":   "PERPLEXITY_API_KEY",
}

new_keys: dict[str, str] = {}
for env_name, vault_name in SOURCES.items():
    v = os.environ.get(env_name)
    if v and vault_name not in new_keys:   # first wins so REAL_ takes precedence
        new_keys[vault_name] = v

if not new_keys:
    sys.exit(
        "No keys to seed. Set one or more of: "
        "REAL_ANTHROPIC_KEY, REAL_OPENAI_KEY, REAL_PERPLEXITY_KEY"
    )

conn = psycopg2.connect(DB_URL)
conn.autocommit = False
with conn.cursor() as cur:
    cur.execute(
        """
        SELECT id, encrypted_credentials FROM integrations
        WHERE workspace_id = %s AND handle = 'env_vars'
        LIMIT 1
        """,
        (WS_ID,),
    )
    row = cur.fetchone()

    if row:
        existing = decrypt(row[1]) or {}
        existing.update(new_keys)
        merged = encrypt(existing)
        cur.execute(
            "UPDATE integrations SET encrypted_credentials = %s WHERE id = %s",
            (merged, row[0]),
        )
        print(f"Merged into env_vars integration {row[0]} for workspace {WS_ID}")
    else:
        creds = encrypt(new_keys)
        cur.execute(
            """
            INSERT INTO integrations
              (id, workspace_id, handle, name, encrypted_credentials, created_at, updated_at)
            VALUES (%s, %s, 'env_vars', 'env-vars', %s, now(), now())
            """,
            (str(uuid.uuid4()), WS_ID, creds),
        )
        print(f"Created env_vars integration for workspace {WS_ID}")
conn.commit()
conn.close()

print(f"Seeded keys: {', '.join(sorted(new_keys))}")
