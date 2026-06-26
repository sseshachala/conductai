"""One-shot: rewrite all env_vars integration credentials with UPPER keys.

Existing local/staging/prod data may have lower-case keys from before the
EnvironmentsManager normalized on input. Proxy + runtime read via case-fold
fallback already, but normalizing now keeps audit/logs clean and means we
can drop the lower fallback later.

Idempotent — re-running on already-upper data is a no-op.

Run:
  cd apps/api
  .venv/bin/python scripts/normalize_env_var_keys.py            # dry-run
  .venv/bin/python scripts/normalize_env_var_keys.py --apply    # write
"""
from __future__ import annotations

import os
import sys

import psycopg2

from app.core.crypto import decrypt, encrypt


DB_URL = os.environ.get("DATABASE_URL", "postgresql://marshal:marshal@localhost:5432/marshal")
APPLY = "--apply" in sys.argv

conn = psycopg2.connect(DB_URL)
conn.autocommit = False

with conn.cursor() as cur:
    cur.execute("""
        SELECT id, workspace_id, encrypted_credentials FROM integrations
        WHERE handle = 'env_vars' AND encrypted_credentials IS NOT NULL
    """)
    rows = cur.fetchall()

    changed = 0
    untouched = 0
    for integration_id, workspace_id, enc in rows:
        try:
            creds = decrypt(enc) or {}
        except Exception:
            continue
        normalized = {k.upper(): v for k, v in creds.items()}
        if normalized == creds:
            untouched += 1
            continue
        keys_renamed = [
            f"{k} → {k.upper()}" for k in creds if k != k.upper()
        ]
        print(f"[{workspace_id}] {integration_id}: {', '.join(keys_renamed)}")
        if APPLY:
            cur.execute(
                "UPDATE integrations SET encrypted_credentials = %s WHERE id = %s",
                (encrypt(normalized), integration_id),
            )
        changed += 1

    print(f"\n{changed} integration(s) {'updated' if APPLY else 'would change'}, {untouched} already canonical.")
    if APPLY:
        conn.commit()
    else:
        print("\nDry run. Re-run with --apply to write.")
conn.close()
