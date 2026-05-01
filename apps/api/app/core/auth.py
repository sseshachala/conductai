"""
Optional Clerk JWT verification middleware.

When CLERK_SECRET_KEY is set, validates Bearer tokens from Clerk.
Falls back to the dev workspace when no key is configured (local dev only).

Usage in routes:
    from app.core.auth import get_workspace_id
    workspace_id: str = Depends(get_workspace_id)
"""
import logging
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

log = logging.getLogger(__name__)

DEV_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"

_bearer = HTTPBearer(auto_error=False)

# Cache Clerk JWKS to avoid fetching on every request
_jwks_cache: dict | None = None


def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache:
        return _jwks_cache
    clerk_domain = settings.clerk_frontend_api or ""
    if not clerk_domain:
        return {}
    try:
        r = httpx.get(f"https://{clerk_domain}/.well-known/jwks.json", timeout=10)
        r.raise_for_status()
        _jwks_cache = r.json()
        return _jwks_cache
    except Exception as e:
        log.warning("Could not fetch Clerk JWKS: %s", e)
        return {}


def _verify_clerk_token(token: str) -> dict | None:
    """Verify a Clerk JWT. Returns claims dict or None if invalid."""
    try:
        import jwt as pyjwt

        jwks = _get_jwks()
        if not jwks:
            return None

        header = pyjwt.get_unverified_header(token)
        key_id = header.get("kid")
        key = next((k for k in jwks.get("keys", []) if k.get("kid") == key_id), None)
        if not key:
            return None

        from jwt.algorithms import RSAAlgorithm
        public_key = RSAAlgorithm.from_jwk(key)
        claims = pyjwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return claims
    except Exception as e:
        log.debug("Clerk token verification failed: %s", e)
        return None


def get_workspace_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> str:
    """
    Dependency that returns the workspace ID for the current request.

    - If CLERK_SECRET_KEY is not set: returns dev workspace ID (no auth)
    - If set and valid JWT: extracts workspace from 'org_id' or 'sub' claim
    - If set and invalid JWT: raises 401
    """
    if not settings.clerk_secret_key:
        return DEV_WORKSPACE_ID

    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header required")

    claims = _verify_clerk_token(credentials.credentials)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # Clerk stores org_id in the session claims when the user has an active org
    workspace_id = claims.get("org_id") or claims.get("sub")
    if not workspace_id:
        raise HTTPException(status_code=401, detail="No workspace in token claims")

    return workspace_id
