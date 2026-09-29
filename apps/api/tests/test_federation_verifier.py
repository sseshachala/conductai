import json
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from pydantic import ValidationError

from app.modules.auth.federation.config import TrustConfig
from app.modules.auth.federation.network import VerificationUnavailable
from app.modules.auth.federation.verifier import InvalidIdentity, KeyCache, verify_access_token


@pytest.fixture(scope="module")
def keys():
    return [rsa.generate_private_key(public_exponent=65537, key_size=2048) for _ in range(2)]


def jwk(key, kid="one"):
    return {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key())), "kid": kid, "alg": "RS256", "use": "sig"}


def config(issuer="https://idp.example", **overrides):
    return TrustConfig(issuer=issuer, audience="conduct", jwks_uri=issuer + "/keys", **overrides)


def token(key, issuer="https://idp.example", kid="one", headers=None, **claims):
    payload = {"iss": issuer, "aud": "conduct", "sub": "user-1", "exp": int(time.time()) + 300, **claims}
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": kid, "typ": "at+jwt", **(headers or {})})


def verify(raw, cfg, cache, **ids):
    return verify_access_token(raw, cfg, workspace_id=ids.get("workspace_id", uuid4()),
                               connection_id=ids.get("connection_id", uuid4()), revision=ids.get("revision", 1), cache=cache)


@pytest.mark.parametrize("issuer", ["https://idp.example", "https://other.example/tenant"])
def test_two_independent_issuers(keys, issuer):
    index = int("other" in issuer)
    cache = KeyCache(fetch=lambda _: {"keys": [jwk(keys[index])]})
    result = verify(token(keys[index], issuer), config(issuer), cache)
    assert result.evidence.issuer == issuer
    assert result.evidence.subject == "user-1"
    assert not hasattr(result, "token")


@pytest.mark.parametrize("change", [
    {"iss": "https://wrong.example"}, {"aud": "wrong"}, {"sub": ""},
    {"exp": 1}, {"nbf": 9999999999}, {"iat": 9999999999}, {"exp": True},
])
def test_invalid_claims(keys, change):
    with pytest.raises(InvalidIdentity):
        verify(token(keys[0], **change), config(), KeyCache(fetch=lambda _: {"keys": [jwk(keys[0])]}))


def test_wrong_signature(keys):
    with pytest.raises(InvalidIdentity):
        verify(token(keys[1]), config(), KeyCache(fetch=lambda _: {"keys": [jwk(keys[0])]}))


@pytest.mark.parametrize("header", [{"typ": "JWT"}, {"jku": "https://attacker.example"}, {"crit": ["custom"]}])
def test_invalid_headers_fail_before_fetch(keys, header):
    def forbidden(_):
        pytest.fail("must not fetch keys")
    with pytest.raises(InvalidIdentity):
        verify(token(keys[0], headers=header), config(), KeyCache(fetch=forbidden))


def test_symmetric_algorithm_denied():
    raw = jwt.encode({"sub": "user"}, "synthetic-test-key-long-enough-for-hmac", algorithm="HS256", headers={"kid": "one"})
    with pytest.raises(InvalidIdentity):
        verify(raw, config(), KeyCache(fetch=lambda _: pytest.fail("unexpected fetch")))


def test_disabled_connection_denied_before_fetch(keys):
    with pytest.raises(InvalidIdentity, match="disabled"):
        verify(token(keys[0]), config(status="disabled"), KeyCache(fetch=lambda _: pytest.fail("unexpected fetch")))


def test_token_use_profile_and_mapped_claims(keys):
    cfg = config(token_profile="token_use_access", claim_mappings=[{"name": "team", "source_claim": "groups"}])
    cache = KeyCache(fetch=lambda _: {"keys": [jwk(keys[0])]})
    raw = token(keys[0], headers={"typ": "JWT"}, token_use="access", groups=["engineering"], private="not-retained")
    result = verify(raw, cfg, cache)
    assert result.attributes[0].values == ("engineering",)
    assert "private" not in repr(result)
    with pytest.raises(InvalidIdentity):
        verify(token(keys[0], token_use="id"), cfg, cache)


def test_rotation_cooldown_and_revision_invalidation(keys):
    clock = [0]
    documents = [{"keys": [jwk(keys[0])]}]
    calls = []
    def fetch(url):
        calls.append(url)
        return documents[0]
    cache = KeyCache(fetch=fetch, clock=lambda: clock[0])
    ids = {"workspace_id": uuid4(), "connection_id": uuid4()}
    verify(token(keys[0]), config(), cache, **ids)
    documents[0] = {"keys": [jwk(keys[1], "two")]}
    with pytest.raises(InvalidIdentity):
        verify(token(keys[1], kid="two"), config(), cache, **ids)
    assert len(calls) == 1
    clock[0] = 11
    verify(token(keys[1], kid="two"), config(), cache, **ids)
    with pytest.raises(InvalidIdentity):
        verify(token(keys[0]), config(), cache, **ids)
    verify(token(keys[1], kid="two"), config(), cache, **ids, revision=2)
    assert len(calls) == 3


def test_concurrent_calls_share_keys_not_principals(keys):
    calls = []
    cache = KeyCache(fetch=lambda url: calls.append(url) or {"keys": [jwk(keys[0])]})
    ids = {"workspace_id": uuid4(), "connection_id": uuid4()}
    def run(index):
        return verify(token(keys[0], sub=f"user-{index}"), config(), cache, **ids).evidence.subject
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert list(pool.map(run, range(8))) == [f"user-{i}" for i in range(8)]
    assert len(calls) == 1
    verify(token(keys[0]), config(), cache, workspace_id=uuid4(), connection_id=ids["connection_id"])
    assert len(calls) == 2


def test_expired_cache_fails_closed_on_outage(keys):
    clock = [0]
    def fetch(_):
        if clock[0]:
            raise VerificationUnavailable("federation_endpoint_unavailable")
        return {"keys": [jwk(keys[0])]}
    cache = KeyCache(fetch=fetch, clock=lambda: clock[0])
    ids = {"workspace_id": uuid4(), "connection_id": uuid4()}
    verify(token(keys[0]), config(), cache, **ids)
    clock[0] = 301
    with pytest.raises(VerificationUnavailable):
        verify(token(keys[0]), config(), cache, **ids)


def test_discovery_cannot_change_trusted_jwks(keys):
    cache = KeyCache(fetch=lambda _: {"issuer": "https://idp.example", "jwks_uri": "https://attacker.example"})
    with pytest.raises(InvalidIdentity, match="discovery_mismatch"):
        verify(token(keys[0]), config(discovery_uri="https://idp.example/.well-known/openid-configuration"), cache)


@pytest.mark.parametrize("overrides", [
    {"issuer": "http://idp.example"}, {"jwks_uri": "https://user:pass@idp.example/keys"},
    {"jwks_uri": "https://idp.example/keys?token=secret"}, {"algorithms": ["HS256"]},
    {"status": "unknown"}, {"claim_mappings": [{"name": "role", "source_claim": "groups"}]},
])
def test_invalid_config(overrides):
    base = {"issuer": "https://idp.example", "jwks_uri": "https://idp.example/keys", "audience": "conduct"}
    with pytest.raises(ValidationError):
        TrustConfig(**(base | overrides))
