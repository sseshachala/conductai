"""Unit tests for the PKCE S256 verifier."""
from __future__ import annotations

import base64
import hashlib

from app.modules.auth.oauth.pkce import verify_s256


def _mk_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def test_verify_ok():
    v = "sample-code-verifier-abc123"
    assert verify_s256(v, _mk_challenge(v)) is True


def test_verify_wrong_verifier():
    v = "verifier-a"
    other = _mk_challenge("verifier-b")
    assert verify_s256(v, other) is False


def test_verify_empty_inputs():
    assert verify_s256("", "x") is False
    assert verify_s256("x", "") is False
    assert verify_s256("", "") is False
