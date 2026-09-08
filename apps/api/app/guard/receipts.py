"""Block receipt URL builder — the deep-link every block response carries.

`build_receipt_url(receipt_id)` returns the workspace-authenticated URL
(requires login). `build_receipt_url(receipt_id, share_token=...)` returns
the anonymous public URL for trial signup users — the token is hashed with
sha256 and the hash is stored on the audit row (see `guard.audit.record`).

Reuses the same `CONDUCT_WEB_URL` env var pattern as `approval_url` in
`app.modules.guard.approval` so trial + workspace + approval deep-links all
resolve against the same host.
"""
from __future__ import annotations

import hashlib
import os
import secrets

SHARE_TOKEN_PREFIX = "cond_bkr_"


def _base_url() -> str:
    return (os.environ.get("CONDUCT_WEB_URL") or "https://conductai.ai").rstrip("/")


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
        return f"{_base_url()}/b/{receipt_id}/{share_token}"
    return f"{_base_url()}/theguard/blocks/{receipt_id}"
