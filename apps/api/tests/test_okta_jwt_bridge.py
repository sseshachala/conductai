"""
Bridge tests for _resolve_okta_jwt (#1056).

The JWT verifier itself is exhaustively tested in test_okta_jwt.py. Here we
test only the bridge decisions: when to return None (fall through), when to
raise 401, and how lifecycle_state gates access.

Verifier is monkeypatched to control the "returns claims" side without
needing real RSA keys / JWKS.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ── Path + env bootstrap ────────────────────────────────────────────────────

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_marshal")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")


def _fake_jwt(iss: str = "https://example.okta.com/oauth2/default", sub: str = "0oaSUB") -> str:
    """Return a valid-shaped (3-segment) JWT with a decodable payload.
    Signature is meaningless — the verifier is monkeypatched in these tests."""
    def _b64u(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    header = _b64u(json.dumps({"alg": "RS256", "typ": "JWT", "kid": "k1"}).encode())
    payload = _b64u(json.dumps({"iss": iss, "sub": sub, "aud": "api://default"}).encode())
    sig = _b64u(b"not-a-real-signature")
    return f"{header}.{payload}.{sig}"


def _integration_row(*, issuer: str, audience: str, enabled: bool, workspace_id: uuid.UUID):
    row = MagicMock()
    row.workspace_id = workspace_id
    row.okta_issuer = issuer
    row.okta_audience = audience
    row.okta_auth_enabled = enabled
    return row


def _ai_row(*, workspace_id: uuid.UUID, source_id: str, lifecycle_state: str = "active"):
    ai = MagicMock()
    ai.workspace_id = workspace_id
    ai.source = "okta"
    ai.source_id = source_id
    ai.lifecycle_state = lifecycle_state
    return ai


def _db_with(integration_rows: list, ai_row=None):
    """Build a Session mock. First .query() → integrations, second → agent_identities."""
    db = MagicMock()
    integration_q = MagicMock()
    integration_q.filter.return_value.all.return_value = integration_rows
    ai_q = MagicMock()
    ai_q.filter.return_value.first.return_value = ai_row
    db.query.side_effect = [integration_q, ai_q]
    return db


# ═══════════════════════════════════════════════════════════════════════════════

def test_non_jwt_shape_returns_none():
    from app.core.auth import _resolve_okta_jwt
    assert _resolve_okta_jwt("cond_agt_whatever", MagicMock()) is None
    assert _resolve_okta_jwt("only.two", MagicMock()) is None
    assert _resolve_okta_jwt("", MagicMock()) is None


def test_undecodable_payload_returns_none():
    from app.core.auth import _resolve_okta_jwt
    assert _resolve_okta_jwt("not.a.jwt", MagicMock()) is None


def test_missing_iss_returns_none():
    from app.core.auth import _resolve_okta_jwt

    def _b64u(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    header = _b64u(json.dumps({"alg": "RS256"}).encode())
    payload = _b64u(json.dumps({"sub": "x"}).encode())  # no iss
    tok = f"{header}.{payload}.sig"
    assert _resolve_okta_jwt(tok, MagicMock()) is None


def test_no_workspace_configured_returns_none_falls_through_to_clerk():
    """If no Integration row matches the iss, return None so caller tries Clerk."""
    from app.core.auth import _resolve_okta_jwt

    tok = _fake_jwt(iss="https://clerk.example.com")
    db = _db_with(integration_rows=[])
    assert _resolve_okta_jwt(tok, db) is None


def test_feature_flag_off_returns_none(monkeypatch):
    """Even with issuer configured, okta_auth_enabled=false → the filter excludes it → None."""
    from app.core.auth import _resolve_okta_jwt

    # Query filter already excludes disabled rows, so we simulate the "no rows" outcome
    tok = _fake_jwt()
    db = _db_with(integration_rows=[])
    assert _resolve_okta_jwt(tok, db) is None


def test_happy_path_returns_identity(monkeypatch):
    import app.core.auth as auth_mod

    ws_id = uuid.uuid4()
    integration = _integration_row(
        issuer="https://example.okta.com/oauth2/default",
        audience="api://default",
        enabled=True,
        workspace_id=ws_id,
    )
    ai = _ai_row(workspace_id=ws_id, source_id="0oaSUB")
    db = _db_with(integration_rows=[integration], ai_row=ai)

    # Monkeypatch the verifier: return claims that pass validation
    def _fake_verify(token, issuer, audience, **kw):
        return {"iss": issuer, "aud": audience, "sub": "0oaSUB", "exp": 9999999999}

    monkeypatch.setattr("app.core.okta_jwt.verify_okta_jwt", _fake_verify)

    result = auth_mod._resolve_okta_jwt(_fake_jwt(sub="0oaSUB"), db)
    assert result is not None
    resolved_ai, clerk_uid = result
    assert resolved_ai is ai
    assert clerk_uid is None  # Okta = machine identity, no clerk user


def test_identity_not_synced_raises_401(monkeypatch):
    from fastapi import HTTPException

    import app.core.auth as auth_mod

    ws_id = uuid.uuid4()
    integration = _integration_row(
        issuer="https://example.okta.com/oauth2/default",
        audience="api://default",
        enabled=True,
        workspace_id=ws_id,
    )
    db = _db_with(integration_rows=[integration], ai_row=None)  # no identity

    monkeypatch.setattr(
        "app.core.okta_jwt.verify_okta_jwt",
        lambda token, issuer, audience, **kw: {"sub": "unknown", "iss": issuer, "aud": audience},
    )

    with pytest.raises(HTTPException) as ei:
        auth_mod._resolve_okta_jwt(_fake_jwt(sub="unknown"), db)
    assert ei.value.status_code == 401
    assert "not synced" in ei.value.detail


def test_deactivated_identity_raises_401(monkeypatch):
    from fastapi import HTTPException

    import app.core.auth as auth_mod

    ws_id = uuid.uuid4()
    integration = _integration_row(
        issuer="https://example.okta.com/oauth2/default",
        audience="api://default",
        enabled=True,
        workspace_id=ws_id,
    )
    ai = _ai_row(workspace_id=ws_id, source_id="0oaSUB", lifecycle_state="deactivated")
    db = _db_with(integration_rows=[integration], ai_row=ai)

    monkeypatch.setattr(
        "app.core.okta_jwt.verify_okta_jwt",
        lambda token, issuer, audience, **kw: {"sub": "0oaSUB", "iss": issuer, "aud": audience},
    )

    with pytest.raises(HTTPException) as ei:
        auth_mod._resolve_okta_jwt(_fake_jwt(), db)
    assert ei.value.status_code == 401
    assert "deactivated" in ei.value.detail


def test_expired_lifecycle_raises_401(monkeypatch):
    from fastapi import HTTPException

    import app.core.auth as auth_mod

    ws_id = uuid.uuid4()
    integration = _integration_row(
        issuer="https://example.okta.com/oauth2/default",
        audience="api://default",
        enabled=True,
        workspace_id=ws_id,
    )
    ai = _ai_row(workspace_id=ws_id, source_id="0oaSUB", lifecycle_state="expired")
    db = _db_with(integration_rows=[integration], ai_row=ai)

    monkeypatch.setattr(
        "app.core.okta_jwt.verify_okta_jwt",
        lambda token, issuer, audience, **kw: {"sub": "0oaSUB", "iss": issuer, "aud": audience},
    )

    with pytest.raises(HTTPException) as ei:
        auth_mod._resolve_okta_jwt(_fake_jwt(), db)
    assert ei.value.status_code == 401
    assert "expired" in ei.value.detail


def test_verify_failure_raises_401(monkeypatch):
    from fastapi import HTTPException

    import app.core.auth as auth_mod
    from app.core.okta_jwt import OktaJWTInvalid

    ws_id = uuid.uuid4()
    integration = _integration_row(
        issuer="https://example.okta.com/oauth2/default",
        audience="api://default",
        enabled=True,
        workspace_id=ws_id,
    )
    db = _db_with(integration_rows=[integration], ai_row=None)

    def _fail(token, issuer, audience, **kw):
        raise OktaJWTInvalid("wrong signature")

    monkeypatch.setattr("app.core.okta_jwt.verify_okta_jwt", _fail)

    with pytest.raises(HTTPException) as ei:
        auth_mod._resolve_okta_jwt(_fake_jwt(), db)
    assert ei.value.status_code == 401
    assert "verification failed" in ei.value.detail


def test_missing_sub_raises_401(monkeypatch):
    from fastapi import HTTPException

    import app.core.auth as auth_mod

    ws_id = uuid.uuid4()
    integration = _integration_row(
        issuer="https://example.okta.com/oauth2/default",
        audience="api://default",
        enabled=True,
        workspace_id=ws_id,
    )
    db = _db_with(integration_rows=[integration], ai_row=None)

    monkeypatch.setattr(
        "app.core.okta_jwt.verify_okta_jwt",
        lambda token, issuer, audience, **kw: {"iss": issuer, "aud": audience},  # no sub
    )

    with pytest.raises(HTTPException) as ei:
        auth_mod._resolve_okta_jwt(_fake_jwt(), db)
    assert ei.value.status_code == 401
    assert "sub" in ei.value.detail
