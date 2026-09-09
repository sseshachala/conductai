"""PKCE (RFC 7636) verification — S256 only.

OAuth 2.1 mandates S256; plain method is rejected. Public MCP clients rely
on PKCE as the sole client-auth mechanism, so this check is load-bearing.
"""
from __future__ import annotations

import base64
import hashlib


def verify_s256(code_verifier: str, code_challenge: str) -> bool:
    """True iff base64url(sha256(code_verifier)) == code_challenge (no padding)."""
    if not code_verifier or not code_challenge:
        return False
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return computed == code_challenge
