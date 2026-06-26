"""Seed a real Anthropic key into a workspace's `env_vars` integration so the
Guard proxy can use it during the smoke test.

Usage:
  WORKSPACE_ID=<uuid> REAL_ANTHROPIC_KEY=sk-ant-… \
    .venv/bin/python scripts/seed_anthropic_key.py

Idempotent — upserts the env_vars integration's encrypted_credentials.
"""
from __future__ import annotations

import json
import os
import sys
import uuid

import psycopg2

from app.core.crypto import encrypt


DB_URL = os.environ.get(
    "DATABASE_URL", "postgresql://marshal:marshal@localhost:5432/marshal"
)
WS_ID = os.environ.get("WORKSPACE_ID")
KEY = os.environ.get("REAL_ANTHROPIC_KEY") or os.environ.get("ANTHROPIC_API_KEY")

if not WS_ID:
    sys.exit("WORKSPACE_ID required (uuid)")
if not KEY:
    sys.exit("REAL_ANTHROPIC_KEY or ANTHROPIC_API_KEY required")

creds = encrypt({"ANTHROPIC_API_KEY": KEY})

conn = psycopg2.connect(DB_URL)
conn.autocommit = False
with conn.cursor() as cur:
    cur.execute(
        """
        SELECT id FROM integrations
        WHERE workspace_id = %s AND handle = 'env_vars'
        LIMIT 1
        """,
        (WS_ID,),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE integrations SET encrypted_credentials = %s WHERE id = %s",
            (creds, row[0]),
        )
        print(f"Updated env_vars integration {row[0]} for workspace {WS_ID}")
    else:
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
print("Anthropic key seeded — proxy can now resolve it.")
