"""
Okta JWT verifier — RS256 only, per-issuer JWKS cache, no algorithm downgrade.

Standalone. Wired into `app.core.auth._resolve_agent_token` by issue #1056.

Non-negotiables (enforced here, tested in tests/test_okta_jwt.py):
- alg MUST be RS256 (HS256, none, symmetric algs are rejected outright)
- iss MUST match exactly
- aud MUST match exactly (string or list per RFC 7519)
- exp MUST be future (30s skew)
- iat/nbf if present, must be past
- Signature verified against a JWKS-fetched RSA public key matching `kid`
- On unknown kid: one JWKS refresh permitted (natural cache-miss path), then fail
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
import structlog

log = structlog.get_logger(__name__)

_JWKS_TTL_S = 3600
_CLOCK_SKEW_S = 30
_HTTP_TIMEOUT_S = 5


class OktaJWTError(Exception):
    """Base for all Okta JWT verification failures."""


class OktaJWTInvalid(OktaJWTError):
    """Malformed, wrong-audience, wrong-signature, bad alg, or unknown key."""


class OktaJWTExpired(OktaJWTError):
    """Token past exp (with clock-skew allowance)."""


class OktaJWTUntrusted(OktaJWTError):
    """Token issuer does not match the configured issuer for this workspace."""


@dataclass
class _CachedJWKS:
    keys: dict[str, Any] = field(default_factory=dict)  # kid -> public key
    fetched_at: float = 0.0


class OktaJWKSCache:
    """Per-issuer JWKS cache. TTL + refresh-on-unknown-kid via natural miss path."""

    def __init__(self, ttl_s: int = _JWKS_TTL_S, http_timeout_s: int = _HTTP_TIMEOUT_S):
        self._ttl = ttl_s
        self._data: dict[str, _CachedJWKS] = {}
        self._lock = threading.Lock()
        # Per-issuer lock: serializes concurrent refreshes for the same issuer
        # so N racing verifiers trigger exactly one JWKS fetch, not N.
        self._issuer_locks: dict[str, threading.Lock] = {}
        # ponytail: shared client — connection pooling, matches auth.py pattern
        self._http = httpx.Client(timeout=http_timeout_s)

    def _lock_for(self, issuer: str) -> threading.Lock:
        with self._lock:
            lk = self._issuer_locks.get(issuer)
            if lk is None:
                lk = threading.Lock()
                self._issuer_locks[issuer] = lk
            return lk

    def _fetch(self, issuer: str) -> dict:
        # ponytail: Okta convention — {issuer}/v1/keys. Non-Okta OIDC would fetch
        # /.well-known/openid-configuration and read jwks_uri; add when we add another provider.
        url = f"{issuer.rstrip('/')}/v1/keys"
        r = self._http.get(url)
        r.raise_for_status()
        return r.json()

    def _load(self, issuer: str) -> dict[str, Any]:
        try:
            jwks = self._fetch(issuer)
        except Exception as e:
            log.warning("okta.jwks.fetch_failed", issuer=issuer, error=str(e))
            raise OktaJWTInvalid(f"jwks fetch failed: {e}") from e
        keys: dict[str, Any] = {}
        for k in jwks.get("keys", []):
            kid = k.get("kid")
            if not kid:
                continue
            try:
                keys[kid] = jwt.PyJWK(k).key
            except Exception as e:  # bad JWK entry — skip, don't fail the whole set
                log.warning("okta.jwks.bad_key", kid=kid, error=str(e))
        with self._lock:
            self._data[issuer] = _CachedJWKS(keys=keys, fetched_at=time.time())
        return keys

    def get_key(self, issuer: str, kid: str) -> Any:
        with self._lock:
            entry = self._data.get(issuer)
            fresh = entry is not None and (time.time() - entry.fetched_at) <= self._ttl
            if fresh and kid in entry.keys:
                return entry.keys[kid]
        # Miss: unknown issuer, expired, or unknown kid. Serialize per-issuer so
        # concurrent verifiers under a rotation trigger exactly one JWKS fetch.
        iss_lock = self._lock_for(issuer)
        with iss_lock:
            # Re-check after acquiring the per-issuer lock — another thread may
            # have refreshed while we were waiting.
            with self._lock:
                entry = self._data.get(issuer)
                fresh = entry is not None and (time.time() - entry.fetched_at) <= self._ttl
                if fresh and kid in entry.keys:
                    return entry.keys[kid]
            keys = self._load(issuer)
        if kid not in keys:
            raise OktaJWTInvalid(f"unknown kid: {kid}")
        return keys[kid]

    def invalidate(self, issuer: str | None = None) -> None:
        with self._lock:
            if issuer is None:
                self._data.clear()
            else:
                self._data.pop(issuer, None)


_default_cache = OktaJWKSCache()


def verify_okta_jwt(
    token: str,
    issuer: str,
    audience: str,
    *,
    cache: OktaJWKSCache | None = None,
    leeway_s: int = _CLOCK_SKEW_S,
) -> dict:
    """
    Verify an Okta-issued JWT and return validated claims.

    Raises OktaJWTError subclasses on any failure. Never returns unverified claims.
    """
    cache = cache or _default_cache

    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as e:
        raise OktaJWTInvalid(f"malformed token: {e}") from e

    alg = header.get("alg")
    if alg != "RS256":
        raise OktaJWTInvalid(f"unsupported alg: {alg!r}")

    kid = header.get("kid")
    if not kid:
        raise OktaJWTInvalid("missing kid")

    key = cache.get_key(issuer, kid)

    try:
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            audience=audience,
            issuer=issuer,
            leeway=leeway_s,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError as e:
        raise OktaJWTExpired("token expired") from e
    except jwt.InvalidIssuerError as e:
        raise OktaJWTUntrusted(f"wrong issuer: {e}") from e
    except jwt.PyJWTError as e:
        raise OktaJWTInvalid(str(e)) from e

    return claims
