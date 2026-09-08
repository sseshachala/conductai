"""Block receipt URL builder — the deep-link every block response carries.

`build_receipt_url(receipt_id)` returns the workspace-authenticated URL
(requires login). `build_receipt_url(receipt_id, share_token=...)` returns
the public URL for trial signup users — the token is hashed with sha256
and the hash is stored on the audit row (see `guard.audit.record`).

`web_base_url()` is the shared `CONDUCT_WEB_URL` reader used by every
deep-link builder in the API (receipts, approvals, customer alerts,
provisioning). Same env var + default across all callers so trial,
workspace, approval, and receipt URLs all resolve against the same host.

The path shape `/theguard/blocks/{id}` and `/b/{id}/{token}` is mirrored in
``packages/conduct-cli/src/conduct_cli/hooks/base.py::hook_receipt_url`` —
if you change either shape here, change it there too. Cross-package
because the CLI hook mints its own receipt id client-side and prints the
URL to stderr before the audit row is written.
"""
from __future__ import annotations

import hashlib
import os
import secrets

SHARE_TOKEN_PREFIX = "cond_bkr_"


DEFAULT_LOCAL_WEB_URL = "http://localhost:3000"


def web_base_url() -> str:
    """The web-app host used by every API-side deep-link builder.

    Resolution order (first non-empty wins):
      1. `CONDUCT_WEB_URL` — legacy override reader, kept for compat with
         approval.py + customer_alert.py which already read it.
      2. `APP_URL` — canonical env var (also feeds `settings.app_url`).
         Prod deploys set this to the public host (Render, Vercel, etc.).
      3. `DEFAULT_LOCAL_WEB_URL` — zero-config default so a dev running
         the API against `next dev` gets clickable block URLs out of the
         box.

    We read env vars directly rather than going through
    `settings.app_url` so we can distinguish "not set" from "set to the
    code default" — otherwise a prod deploy that sets APP_URL to the
    same string as the code default would fall through to localhost.

    Trailing slash stripped so callers can safely append paths."""
    for var in ("CONDUCT_WEB_URL", "APP_URL"):
        val = os.environ.get(var)
        if val:
            return val.rstrip("/")
    return DEFAULT_LOCAL_WEB_URL


# Backwards-compat alias — earlier PRs referenced the private name.
_base_url = web_base_url


def mint_share_token() -> tuple[str, str]:
    """Return (raw_token, sha256_hash). Store the hash on the audit row,
    hand the raw back to the caller (embedded in the receipt URL)."""
    raw = SHARE_TOKEN_PREFIX + secrets.token_urlsafe(24)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


def hash_share_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def build_receipt_url(receipt_id: str, share_token: str | None = None) -> str:
    """Workspace URL requires login; public URL embeds the raw token in the path."""
    if share_token:
        return f"{web_base_url()}/b/{receipt_id}/{share_token}"
    return f"{web_base_url()}/theguard/blocks/{receipt_id}"
