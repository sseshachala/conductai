"""
Optional Clerk JWT verification middleware.

When CLERK_SECRET_KEY is set, validates Bearer tokens from Clerk.
Falls back to the dev workspace when no key is configured (local dev only).

Usage in routes:
    from app.core.auth import get_workspace_id, get_user_id
    workspace_id: str = Depends(get_workspace_id)
    user_id: str = Depends(get_user_id)
"""
import logging
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

log = logging.getLogger(__name__)

DEV_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
DEV_USER_ID = "dev"

_bearer = HTTPBearer(auto_error=False)

_jwks_cache: dict | None = None


def _fetch_jwks() -> dict:
    clerk_domain = settings.clerk_frontend_api or ""
    if not clerk_domain:
        return {}
    try:
        r = httpx.get(f"https://{clerk_domain}/.well-known/jwks.json", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("Could not fetch Clerk JWKS: %s", e)
        return {}


def _get_jwks(force_refresh: bool = False) -> dict:
    global _jwks_cache
    if _jwks_cache and not force_refresh:
        return _jwks_cache
    _jwks_cache = _fetch_jwks()
    return _jwks_cache


def _verify_clerk_token(token: str) -> dict | None:
    try:
        import jwt as pyjwt
        from jwt.algorithms import RSAAlgorithm

        header = pyjwt.get_unverified_header(token)
        key_id = header.get("kid")

        # Try cached JWKS first, refresh once if kid not found (handles key rotation)
        for force in (False, True):
            jwks = _get_jwks(force_refresh=force)
            key = next((k for k in jwks.get("keys", []) if k.get("kid") == key_id), None)
            if key:
                break
        if not key:
            log.warning("Clerk JWKS has no key matching kid=%s", key_id)
            return None

        public_key = RSAAlgorithm.from_jwk(key)
        claims = pyjwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
            leeway=30,  # tolerate up to 30s clock skew
        )
        return claims
    except Exception as e:
        log.warning("Clerk token verification failed: %s", e)
        return None


def _clerk_enabled() -> bool:
    return bool(settings.clerk_secret_key and settings.clerk_frontend_api)


def get_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> str:
    """Returns the Clerk user_id (sub claim), or 'dev' in local dev mode."""
    if not _clerk_enabled():
        return DEV_USER_ID

    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header required")

    claims = _verify_clerk_token(credentials.credentials)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="No user ID in token")

    return user_id


def get_workspace_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    x_workspace_id: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> str:
    """
    Returns the active workspace/project ID for the request.

    Resolution order:
    1. X-Workspace-ID header (explicit project selection from frontend)
    2. Clerk JWT org_id or sub (single-workspace-per-user fallback)
    3. Dev workspace (when Clerk is not configured)

    When Clerk is enabled, the workspace must exist and be owned by the user
    — validated at the router level for project-scoped endpoints.
    """
    if not _clerk_enabled():
        return x_workspace_id or DEV_WORKSPACE_ID

    # CLI / server-to-server API key bypasses Clerk
    if x_api_key and settings.cli_api_key and x_api_key == settings.cli_api_key:
        return settings.cli_workspace_id or x_workspace_id or DEV_WORKSPACE_ID

    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header required")

    claims = _verify_clerk_token(credentials.credentials)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    # If the frontend passed an explicit project, use it (ownership validated by caller)
    if x_workspace_id:
        return x_workspace_id

    workspace_id = claims.get("org_id") or claims.get("sub")
    if not workspace_id:
        raise HTTPException(status_code=401, detail="No workspace in token claims")

    return workspace_id
