"""Verification only. Success is not permission to invoke a tool or model."""
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

import jwt

from app.core.jwt_verification import decode_rs256
from .config import TrustConfig
from .contracts import VerificationEvidence, VerifiedAttribute
from .network import VerificationUnavailable, fetch_json

KEY_TTL_SECONDS = 300
REFRESH_COOLDOWN_SECONDS = 10
MAX_CONNECTIONS = 128
MAX_TOKEN_BYTES = 16384


class InvalidIdentity(Exception):
    """Safe authentication failure, without raw evidence."""


@dataclass(frozen=True)
class VerifiedSubject:
    evidence: VerificationEvidence
    attributes: tuple[VerifiedAttribute, ...]


class KeyCache:
    def __init__(self, fetch=fetch_json, clock=time.monotonic):
        self.fetch = fetch
        self.clock = clock
        self._entries = OrderedDict()
        self._attempts = OrderedDict()
        self._lock = threading.Lock()

    def key(self, workspace_id: UUID, connection_id: UUID, revision: int, config: TrustConfig, kid: str | None):
        # Include trust configuration, tenant and revision. Never cache principals.
        cache_key = (workspace_id, connection_id, revision, config.model_dump_json())
        with self._lock:
            now = self.clock()
            entry = self._entries.get(cache_key)
            if entry and now - entry[0] < KEY_TTL_SECONDS and (kid is None or kid in entry[1]):
                self._entries.move_to_end(cache_key)
                if kid is None and not entry[1]:
                    raise VerificationUnavailable("federation_invalid_jwks")
                return len(entry[1]) if kid is None else entry[1][kid]
            attempt = self._attempts.get(cache_key)
            if attempt is not None and now - attempt < REFRESH_COOLDOWN_SECONDS:
                if entry and now - entry[0] < KEY_TTL_SECONDS:
                    raise InvalidIdentity("federation_unknown_key")
                raise VerificationUnavailable("federation_key_refresh_throttled")
            self._attempts[cache_key] = now
            self._attempts.move_to_end(cache_key)
            while len(self._attempts) > MAX_CONNECTIONS:
                self._attempts.popitem(last=False)
            if config.discovery_uri:
                metadata = self.fetch(config.discovery_uri)
                if metadata.get("issuer") != config.issuer or metadata.get("jwks_uri") != config.jwks_uri:
                    raise InvalidIdentity("federation_discovery_mismatch")
            document = self.fetch(config.jwks_uri)
            raw_keys = document.get("keys")
            if not isinstance(raw_keys, list) or not 1 <= len(raw_keys) <= 32:
                raise VerificationUnavailable("federation_invalid_jwks")
            keys = {}
            for raw in raw_keys:
                if not isinstance(raw, dict):
                    continue
                key_id = raw.get("kid")
                if (not isinstance(key_id, str) or not 1 <= len(key_id) <= 256
                        or raw.get("kty") != "RSA" or raw.get("alg", "RS256") != "RS256"
                        or raw.get("use", "sig") != "sig"
                        or "d" in raw or ("key_ops" in raw and raw["key_ops"] != ["verify"])):
                    continue
                if key_id in keys:
                    raise VerificationUnavailable("federation_duplicate_key")
                try:
                    key = jwt.PyJWK(raw).key
                    if key.key_size < 2048:
                        continue
                    keys[key_id] = key
                except (ValueError, TypeError, jwt.PyJWTError):
                    continue
            self._entries[cache_key] = (self.clock(), keys)
            self._entries.move_to_end(cache_key)
            while len(self._entries) > MAX_CONNECTIONS:
                self._entries.popitem(last=False)
            if kid is None:
                if not keys:
                    raise VerificationUnavailable("federation_invalid_jwks")
                return len(keys)
            if kid not in keys:
                raise InvalidIdentity("federation_unknown_key")
            return keys[kid]


DEFAULT_CACHE = KeyCache()


def verify_access_token(
    token: str, config: TrustConfig, *, workspace_id: UUID, connection_id: UUID,
    revision: int, cache: KeyCache = DEFAULT_CACHE,
) -> VerifiedSubject:
    if config.status == "disabled":
        raise InvalidIdentity("federation_connection_disabled")
    try:
        if not isinstance(token, str) or len(token.encode()) > MAX_TOKEN_BYTES:
            raise InvalidIdentity("federation_invalid_token")
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if header.get("alg") != "RS256" or not isinstance(kid, str) or not 1 <= len(kid) <= 256:
            raise InvalidIdentity("federation_invalid_header")
        if any(name in header for name in ("jku", "jwk", "x5u", "crit")):
            raise InvalidIdentity("federation_unsupported_header")
        if config.token_profile == "at+jwt" and header.get("typ") != "at+jwt":
            raise InvalidIdentity("federation_wrong_token_purpose")
        key = cache.key(workspace_id, connection_id, revision, config, kid)
        claims = decode_rs256(token, key, config.issuer, config.audience, leeway=0)
        if config.token_profile == "token_use_access" and claims.get("token_use") != "access":
            raise InvalidIdentity("federation_wrong_token_purpose")
        if not isinstance(claims.get("sub"), str) or not claims["sub"].strip():
            raise InvalidIdentity("federation_invalid_subject")
        if isinstance(claims["exp"], bool) or not isinstance(claims["exp"], (int, float)):
            raise InvalidIdentity("federation_invalid_expiry")
        attributes = []
        for mapping in config.claim_mappings:
            if mapping.source_claim not in claims:
                continue
            value = claims[mapping.source_claim]
            values = [value] if isinstance(value, str) else value
            if not isinstance(values, list) or len(values) > 64 or any(not isinstance(v, str) for v in values):
                raise InvalidIdentity("federation_invalid_mapped_claim")
            attributes.append(VerifiedAttribute(name=mapping.name, source_claim=mapping.source_claim, values=tuple(values)))
        evidence = VerificationEvidence(
            workspace_id=workspace_id, connection_id=connection_id,
            issuer=claims["iss"], subject=claims["sub"], method="oauth_access_token",
            audience=config.audience, mapping_version=str(revision),
            verified_at=datetime.now(timezone.utc),
            expires_at=datetime.fromtimestamp(claims["exp"], timezone.utc),
        )
        return VerifiedSubject(evidence=evidence, attributes=tuple(attributes))
    except (jwt.PyJWTError, ValueError, TypeError, OverflowError):
        raise InvalidIdentity("federation_invalid_token") from None
