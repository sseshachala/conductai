"""Static deployment trust for signed proxy-to-console identity evidence."""
import json
import ssl
from functools import lru_cache
from urllib.parse import urlsplit
from uuid import UUID

import httpx
import jwt
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.jwt_verification import decode_rs256
from app.modules.auth.federation.network import VerificationUnavailable
from app.modules.auth.federation.verifier import InvalidIdentity, KeyCache, MAX_TOKEN_BYTES


class ConsoleTrust(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    issuer: str
    audience: str = Field(min_length=1, max_length=255)
    jwks_uri: str
    discovery_uri: None = None
    ca_file: str | None = None

    @field_validator("issuer", "jwks_uri")
    @classmethod
    def endpoint(cls, value: str) -> str:
        url = urlsplit(value)
        if (value != value.strip() or any(ord(c) < 33 or ord(c) == 127 for c in value)
                or "\\" in value or url.scheme != "https" or not url.hostname
                or url.username is not None or url.password is not None
                or url.query or url.fragment):
            raise ValueError("console trust endpoints require HTTPS without credentials, query or fragment")
        # These URLs are deployment-admin supplied, never workspace/user supplied.
        # Internal DNS and private CAs are intentional; federation SSRF rules stay unchanged.
        return value


def deployment_fetch(trust: ConsoleTrust, url: str) -> dict:
    if url != trust.jwks_uri:
        raise VerificationUnavailable("console_unconfigured_key_endpoint")
    try:
        context = ssl.create_default_context(cafile=trust.ca_file)
        with httpx.Client(verify=context, trust_env=False, follow_redirects=False, timeout=5) as client:
            with client.stream("GET", url, headers={"Accept": "application/json"}) as response:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise ValueError("oversized key document")
        document = json.loads(body)
        if not isinstance(document, dict):
            raise ValueError("invalid key document")
        return document
    except (httpx.HTTPError, OSError, ValueError):
        raise VerificationUnavailable("console_keys_unavailable") from None


@lru_cache(maxsize=4)
def key_cache(trust: ConsoleTrust) -> KeyCache:
    return KeyCache(fetch=lambda url: deployment_fetch(trust, url))


def verify_proxy_identity(token: str, trust: ConsoleTrust, *, cache: KeyCache | None = None) -> dict:
    """Validate Keycloak ID-token evidence, not an OAuth API access token.

    The OIDC proxy owns the authorization-code flow and nonce/state/PKCE checks.
    Its dedicated client must emit ID tokens with the Keycloak `typ=ID` claim.
    Other provider profiles need an explicit reviewed adapter, never a fallback.
    """
    try:
        if not isinstance(token, str) or len(token.encode()) > MAX_TOKEN_BYTES:
            raise InvalidIdentity("console_invalid_token")
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if (header.get("alg") != "RS256" or header.get("typ") not in (None, "JWT")
                or not isinstance(kid, str) or not 1 <= len(kid) <= 256
                or any(name in header for name in ("jku", "jwk", "x5u", "crit"))):
            raise InvalidIdentity("console_invalid_header")
        keys = cache if cache is not None else key_cache(trust)
        key = keys.key(UUID(int=0), UUID(int=0), 1, trust, kid)
        claims = decode_rs256(token, key, trust.issuer, trust.audience, leeway=0)
        if claims.get("typ") != "ID" or claims.get("azp") != trust.audience:
            raise InvalidIdentity("console_wrong_token_purpose")
        if not isinstance(claims.get("sub"), str) or not claims["sub"].strip():
            raise InvalidIdentity("console_invalid_subject")
        for name in ("iat", "exp"):
            if isinstance(claims.get(name), bool) or not isinstance(claims.get(name), int):
                raise InvalidIdentity("console_invalid_lifetime")
        if claims["exp"] <= claims["iat"]:
            raise InvalidIdentity("console_invalid_lifetime")
        return claims
    except (jwt.PyJWTError, ValueError, TypeError, OverflowError):
        raise InvalidIdentity("console_invalid_token") from None
