"""
Tests for app.core.okta_jwt — 13 cases from issue #1055 acceptance criteria.

No network. RSA keys generated in-fixture, JWKS fetch monkeypatched on the cache.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.core.okta_jwt import (
    OktaJWKSCache,
    OktaJWTExpired,
    OktaJWTInvalid,
    OktaJWTUntrusted,
    verify_okta_jwt,
)

ISSUER = "https://example.okta.com/oauth2/default"
AUD = "api://default"
KID = "test-kid-1"


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def rsa_key_2():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _jwk_pub(priv, kid: str) -> dict:
    d = json.loads(pyjwt.algorithms.RSAAlgorithm.to_jwk(priv.public_key()))
    d["kid"] = kid
    d["alg"] = "RS256"
    d["use"] = "sig"
    return d


def _base_claims(**overrides) -> dict:
    now = int(time.time())
    c = {
        "iss": ISSUER,
        "aud": AUD,
        "sub": "0oa1677gbczxbjmcI698",
        "iat": now - 5,
        "exp": now + 300,
    }
    c.update(overrides)
    return c


def _make_token(priv, claims: dict, *, kid: str | None = KID, alg: str = "RS256", key=None) -> str:
    headers = {"kid": kid} if kid else None
    signing_key = key if key is not None else priv
    return pyjwt.encode(claims, signing_key, algorithm=alg, headers=headers)


@pytest.fixture
def cache_with_key(rsa_key, monkeypatch):
    cache = OktaJWKSCache(ttl_s=60)
    call_count = {"n": 0}

    def _fake_fetch(issuer: str) -> dict:
        call_count["n"] += 1
        return {"keys": [_jwk_pub(rsa_key, KID)]}

    monkeypatch.setattr(cache, "_fetch", _fake_fetch)
    cache.calls = call_count  # type: ignore[attr-defined]
    return cache


# 1
def test_valid_jwt_returns_claims(rsa_key, cache_with_key):
    tok = _make_token(rsa_key, _base_claims())
    claims = verify_okta_jwt(tok, ISSUER, AUD, cache=cache_with_key)
    assert claims["sub"] == "0oa1677gbczxbjmcI698"
    assert claims["iss"] == ISSUER
    assert claims["aud"] == AUD


# 2
def test_wrong_signature_rejected(rsa_key_2, cache_with_key):
    tok = _make_token(rsa_key_2, _base_claims())  # signed by different key
    with pytest.raises(OktaJWTInvalid):
        verify_okta_jwt(tok, ISSUER, AUD, cache=cache_with_key)


# 3
def test_expired_token_raises_expired(rsa_key, cache_with_key):
    now = int(time.time())
    tok = _make_token(rsa_key, _base_claims(exp=now - 120, iat=now - 3600))
    with pytest.raises(OktaJWTExpired):
        verify_okta_jwt(tok, ISSUER, AUD, cache=cache_with_key)


# 4
def test_not_yet_valid_nbf_future(rsa_key, cache_with_key):
    tok = _make_token(rsa_key, _base_claims(nbf=int(time.time()) + 300))
    with pytest.raises(OktaJWTInvalid):
        verify_okta_jwt(tok, ISSUER, AUD, cache=cache_with_key)


# 5
def test_wrong_issuer_untrusted(rsa_key, cache_with_key):
    tok = _make_token(rsa_key, _base_claims(iss="https://evil.example.com/oauth2/default"))
    with pytest.raises(OktaJWTUntrusted):
        verify_okta_jwt(tok, ISSUER, AUD, cache=cache_with_key)


# 6
def test_wrong_audience_invalid(rsa_key, cache_with_key):
    tok = _make_token(rsa_key, _base_claims(aud="api://wrong"))
    with pytest.raises(OktaJWTInvalid):
        verify_okta_jwt(tok, ISSUER, AUD, cache=cache_with_key)


# 7
def test_alg_none_rejected(cache_with_key):
    # alg=none — classic no-signature attack
    tok = pyjwt.encode(_base_claims(), key="", algorithm="none", headers={"kid": KID})
    with pytest.raises(OktaJWTInvalid):
        verify_okta_jwt(tok, ISSUER, AUD, cache=cache_with_key)


# 8
def test_hs256_downgrade_rejected(rsa_key, cache_with_key):
    # Classic algorithm-confusion: attacker hand-builds an HS256 token using the
    # public key PEM as the shared secret. PyJWT's `encode` refuses to do this,
    # so we construct the wire format directly — that's what an attacker does.
    pub_pem = rsa_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )

    def _b64u(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    header = _b64u(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KID}).encode())
    payload = _b64u(json.dumps(_base_claims()).encode())
    signing_input = f"{header}.{payload}".encode()
    sig = _b64u(hmac.new(pub_pem, signing_input, hashlib.sha256).digest())
    tok = f"{header}.{payload}.{sig}"

    with pytest.raises(OktaJWTInvalid):
        verify_okta_jwt(tok, ISSUER, AUD, cache=cache_with_key)


# 9
def test_missing_kid_rejected(rsa_key, cache_with_key):
    tok = _make_token(rsa_key, _base_claims(), kid=None)
    with pytest.raises(OktaJWTInvalid):
        verify_okta_jwt(tok, ISSUER, AUD, cache=cache_with_key)


# 10
def test_unknown_kid_triggers_refresh_then_succeeds(rsa_key, rsa_key_2, monkeypatch):
    cache = OktaJWKSCache(ttl_s=60)
    call_count = {"n": 0}

    def _fake_fetch(issuer: str) -> dict:
        call_count["n"] += 1
        if call_count["n"] == 1:
            return {"keys": [_jwk_pub(rsa_key, KID)]}
        # rotation: second fetch includes the new kid
        return {"keys": [_jwk_pub(rsa_key, KID), _jwk_pub(rsa_key_2, "new-kid")]}

    monkeypatch.setattr(cache, "_fetch", _fake_fetch)

    # Prime cache with the old JWKS
    verify_okta_jwt(_make_token(rsa_key, _base_claims(), kid=KID), ISSUER, AUD, cache=cache)
    assert call_count["n"] == 1

    # New-kid token triggers a fresh fetch (unknown-kid path) and succeeds
    claims = verify_okta_jwt(
        _make_token(rsa_key_2, _base_claims(), kid="new-kid"),
        ISSUER,
        AUD,
        cache=cache,
    )
    assert claims["sub"] == "0oa1677gbczxbjmcI698"
    assert call_count["n"] == 2


# 11
def test_cache_hit_no_second_fetch(rsa_key, cache_with_key):
    tok = _make_token(rsa_key, _base_claims())
    verify_okta_jwt(tok, ISSUER, AUD, cache=cache_with_key)
    verify_okta_jwt(tok, ISSUER, AUD, cache=cache_with_key)
    assert cache_with_key.calls["n"] == 1


# 12
def test_cache_expires_and_refetches(rsa_key, monkeypatch):
    cache = OktaJWKSCache(ttl_s=1)
    call_count = {"n": 0}

    def _fake_fetch(issuer: str) -> dict:
        call_count["n"] += 1
        return {"keys": [_jwk_pub(rsa_key, KID)]}

    monkeypatch.setattr(cache, "_fetch", _fake_fetch)

    tok = _make_token(rsa_key, _base_claims())
    verify_okta_jwt(tok, ISSUER, AUD, cache=cache)
    time.sleep(1.2)
    verify_okta_jwt(tok, ISSUER, AUD, cache=cache)
    assert call_count["n"] == 2


# 13
def test_jwks_unreachable_typed_error_no_accept(rsa_key, monkeypatch):
    cache = OktaJWKSCache(ttl_s=60)

    def _boom(issuer: str) -> dict:
        raise ConnectionError("network down")

    monkeypatch.setattr(cache, "_fetch", _boom)

    tok = _make_token(rsa_key, _base_claims())
    with pytest.raises(OktaJWTInvalid):
        verify_okta_jwt(tok, ISSUER, AUD, cache=cache)
