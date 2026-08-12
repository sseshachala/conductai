"""End-to-end tests for GET /auth/whoami via TestClient.

Covers the four token kinds the router knows: cond_agt_, cond_api_, JWT-shape
matching an Okta issuer (→ okta_jwt), and JWT-shape falling through (→ clerk).
"""
from __future__ import annotations

import base64
import json
import os
import uuid
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_marshal")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-dummy")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

import app.models.environment  # noqa: F401,E402
import app.models.project      # noqa: F401,E402
import app.models.run          # noqa: F401,E402
import app.models.workspace    # noqa: F401,E402

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.auth import get_workspace_id  # noqa: E402
from app.core.database import get_db  # noqa: E402


WS_ID = str(uuid.uuid4())


def _override_db(db_mock):
    def _get_db():
        yield db_mock
    return _get_db


def _client(db_mock):
    app.dependency_overrides[get_db] = _override_db(db_mock)
    app.dependency_overrides[get_workspace_id] = lambda: WS_ID
    return TestClient(app)


def _cleanup():
    app.dependency_overrides.clear()


def _fake_jwt(iss: str = "https://example.okta.com/oauth2/default", sub: str = "0oaSUB") -> str:
    def _b64u(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    header = _b64u(json.dumps({"alg": "RS256", "typ": "JWT", "kid": "k1"}).encode())
    payload = _b64u(json.dumps({"iss": iss, "sub": sub, "aud": "api://default"}).encode())
    return f"{header}.{payload}.sig"


def test_whoami_returns_unknown_without_bearer():
    try:
        client = _client(MagicMock())
        r = client.get(f"/auth/whoami?workspace_id={WS_ID}")
        assert r.status_code == 200
        data = r.json()
        assert data["token_kind"] == "unknown"
        assert data["identity"] is None
    finally:
        _cleanup()


def test_whoami_cond_agt_token_returns_identity(monkeypatch):
    try:
        ai = MagicMock()
        ai.id = "id-1"
        ai.name = "Prod Bot"
        ai.source = "conduct"
        ai.source_id = None
        ai.lifecycle_state = "active"
        monkeypatch.setattr(
            "app.routers.whoami._resolve_agent_token",
            lambda token, db: (ai, "user_abc"),
        )
        client = _client(MagicMock())
        r = client.get(
            f"/auth/whoami?workspace_id={WS_ID}",
            headers={"Authorization": "Bearer cond_agt_test123"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["token_kind"] == "cond_agt"
        assert data["identity"]["id"] == "id-1"
        assert data["identity"]["clerk_user_id"] == "user_abc"
    finally:
        _cleanup()


def test_whoami_jwt_matching_okta_issuer_returns_okta_jwt(monkeypatch):
    try:
        ai = MagicMock()
        ai.id = "id-okta"
        ai.name = "Okta App"
        ai.source = "okta"
        ai.source_id = "0oaSUB"
        ai.lifecycle_state = "active"
        # Bridge returns (identity, None) — clerk_user_id is always None for Okta.
        monkeypatch.setattr(
            "app.routers.whoami._resolve_okta_jwt",
            lambda token, db: (ai, None),
        )
        client = _client(MagicMock())
        r = client.get(
            f"/auth/whoami?workspace_id={WS_ID}",
            headers={"Authorization": f"Bearer {_fake_jwt()}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["token_kind"] == "okta_jwt"
        assert data["identity"]["source"] == "okta"
        assert data["identity"]["clerk_user_id"] is None
    finally:
        _cleanup()


def test_whoami_jwt_no_matching_issuer_returns_clerk(monkeypatch):
    """JWT shape but issuer doesn't match any Okta integration → 'clerk'."""
    try:
        monkeypatch.setattr(
            "app.routers.whoami._resolve_okta_jwt",
            lambda token, db: None,
        )
        client = _client(MagicMock())
        r = client.get(
            f"/auth/whoami?workspace_id={WS_ID}",
            headers={"Authorization": f"Bearer {_fake_jwt(iss='https://clerk.example.com')}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["token_kind"] == "clerk"
        assert data["identity"] is None
    finally:
        _cleanup()
