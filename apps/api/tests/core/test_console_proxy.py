"""Cryptographic console handoff tests; no external IdP or production credentials."""
import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.console import router as routes
from app.modules.auth.console.session import mint_session, verify_session
from app.modules.auth.console.trust import ConsoleTrust, deployment_fetch, verify_proxy_identity
from app.modules.auth.federation.network import VerificationUnavailable
from app.modules.auth.federation.verifier import InvalidIdentity, KeyCache

ISSUER = "https://keycloak.internal/realms/console"
CLIENT = "conduct-console"
TRUST = ConsoleTrust(issuer=ISSUER, audience=CLIENT, jwks_uri=ISSUER + "/protocol/openid-connect/certs")


@pytest.fixture
def signer():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())), "kid": "fixture"}
    cache = KeyCache(fetch=lambda _: {"keys": [jwk]})

    def token(**overrides):
        now = int(time.time())
        claims = {"iss": ISSUER, "aud": CLIENT, "azp": CLIENT, "sub": "alice",
                  "typ": "ID", "iat": now, "exp": now + 300, **overrides}
        return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "fixture"})
    return token, cache


@pytest.fixture
def proxy(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "proxy")
    monkeypatch.setattr(settings, "console_oidc_issuer", ISSUER)
    monkeypatch.setattr(settings, "console_proxy_secret", "unit-test-only-" + "x" * 32)
    row = SimpleNamespace(id=uuid4(), issuer=ISSUER, subject="alice", user_id="oidc_alice", display_name="Alice")
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = row
    return row, db


def test_signed_keycloak_identity(signer):
    token, cache = signer
    assert verify_proxy_identity(token(), TRUST, cache=cache)["sub"] == "alice"


@pytest.mark.parametrize("claims", [{"iss": "https://other.invalid"}, {"aud": "other"},
    {"azp": "other"}, {"typ": "Bearer"}, {"typ": None}, {"sub": ""}, {"sub": []},
    {"exp": 1}, {"exp": True}, {"iat": "1"}, {"iat": int(time.time()) + 1000}])
def test_reject_wrong_identity_purpose_and_claims(signer, claims):
    token, cache = signer
    with pytest.raises(InvalidIdentity):
        verify_proxy_identity(token(**claims), TRUST, cache=cache)


def test_forged_signature_rejected(signer):
    token, cache = signer
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    claims = jwt.decode(token(), options={"verify_signature": False})
    forged = jwt.encode(claims, other_key, algorithm="RS256", headers={"kid": "fixture"})
    with pytest.raises(InvalidIdentity):
        verify_proxy_identity(forged, TRUST, cache=cache)


@pytest.mark.parametrize("url", ["http://internal/keys", "https://user:password@internal/keys", "https://internal/keys?x=1",
                                 "https://internal/keys#x", "https://internal/\\keys"])
def test_unacceptable_deployment_endpoint(url):
    with pytest.raises(ValidationError):
        ConsoleTrust(issuer=ISSUER, audience=CLIENT, jwks_uri=url)


def test_no_arbitrary_key_fetch():
    with pytest.raises(VerificationUnavailable):
        deployment_fetch(TRUST, "https://unconfigured.invalid/keys")


def test_session_is_bounded_and_has_no_external_evidence(proxy):
    row, db = proxy
    session = mint_session(row, int(time.time()) + 20)
    claims = jwt.decode(session["token"], options={"verify_signature": False})
    assert 0 < claims["exp"] - claims["iat"] <= 20
    assert "roles" not in claims and "org_id" not in claims
    assert verify_session(session["token"], db) == {"sub": "oidc_alice", "external_subject": "alice", "external_issuer": ISSUER}


def test_disabled_mapping_invalidates_existing_session(proxy):
    row, db = proxy
    token = mint_session(row, int(time.time()) + 300)["token"]
    db.query.return_value.filter_by.return_value.first.return_value = None
    with pytest.raises(HTTPException) as error:
        verify_session(token, db)
    assert error.value.status_code == 401


def test_session_not_accepted_in_clerk_mode(proxy, monkeypatch):
    row, db = proxy
    token = mint_session(row, int(time.time()) + 300)["token"]
    monkeypatch.setattr(settings, "auth_mode", "clerk")
    with pytest.raises(HTTPException):
        verify_session(token, db)


def test_session_rejected_after_trust_or_secret_change(proxy, monkeypatch):
    row, db = proxy
    token = mint_session(row, int(time.time()) + 300)["token"]
    monkeypatch.setattr(settings, "console_oidc_issuer", "https://different.invalid")
    with pytest.raises(HTTPException):
        verify_session(token, db)
    monkeypatch.setattr(settings, "console_oidc_issuer", ISSUER)
    monkeypatch.setattr(settings, "console_proxy_secret", "another-fixture-" + "y" * 32)
    with pytest.raises(HTTPException):
        verify_session(token, db)


def test_exchange_requires_both_trusted_server_and_signed_user(proxy, signer, monkeypatch):
    row, db = proxy
    token, cache = signer
    monkeypatch.setattr(routes, "configured_trust", lambda: TRUST)
    monkeypatch.setattr(routes, "verify_proxy_identity", lambda value, trust: verify_proxy_identity(value, trust, cache=cache))
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        assert client.post("/auth/console/session", json={"identity_token": token()}).status_code == 401
        headers = {"X-Conduct-Proxy-Secret": settings.console_proxy_secret}
        assert client.post("/auth/console/session", headers=headers, json={"identity_token": "forged"}).status_code == 401
        response = client.post("/auth/console/session", headers=headers, json={"identity_token": token()})
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        assert response.json()["user"]["id"] == row.user_id
        db.query.return_value.filter_by.return_value.first.return_value = None
        assert client.post("/auth/console/session", headers=headers, json={"identity_token": token()}).status_code == 403
