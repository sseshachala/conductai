"""
Optional Clerk JWT verification middleware.

When CLERK_SECRET_KEY is set, validates Bearer tokens from Clerk.
Falls back to the dev workspace when no key is configured (local dev only).

Usage in routes:
    from app.core.auth import get_workspace_id, get_user_id, require_workspace_role
    workspace_id: str = Depends(get_workspace_id)
    user_id: str = Depends(get_user_id)
    # role-gated:
    _: str = Depends(require_workspace_role("admin"))
"""
import logging
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db

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


@lru_cache(maxsize=512)
def get_clerk_user_email(user_id: str) -> str | None:
    """Fetch the primary email address for a Clerk user via the Clerk REST API.

    Result is cached in-process (LRU, 512 entries) — email addresses rarely
    change and the cache is only invalidated by process restart.
    """
    if not settings.clerk_secret_key or not user_id:
        return None
    try:
        r = httpx.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
            timeout=5,
        )
        if not r.is_success:
            return None
        data = r.json()
        primary_id = data.get("primary_email_address_id")
        for e in data.get("email_addresses", []):
            if e.get("id") == primary_id:
                return e.get("email_address")
        emails = data.get("email_addresses", [])
        return emails[0].get("email_address") if emails else None
    except Exception as e:
        log.warning("Could not fetch Clerk user email for %s: %s", user_id, e)
        return None


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


def _assert_workspace_member(db: Session, workspace_id: str, user_id: str) -> None:
    """Raises 403 if user is not a member of the workspace (checks both join table and legacy owner_id)."""
    from sqlalchemy import text
    row = db.execute(
        text("""
            SELECT 1 FROM workspace_users
            WHERE workspace_id = :ws AND clerk_user_id = :uid
            UNION
            SELECT 1 FROM workspaces
            WHERE id = :ws AND owner_id = :uid
            LIMIT 1
        """),
        {"ws": workspace_id, "uid": user_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")


def get_workspace_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    x_workspace_id: Annotated[str | None, Header()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> str:
    """
    Returns the active workspace/project ID for the request.

    Resolution order:
    1. X-Workspace-ID header (explicit project selection) — membership validated against DB
    2. Clerk JWT org_id or sub (single-workspace-per-user fallback)
    3. Dev workspace (when Clerk is not configured)
    """
    if not _clerk_enabled():
        return x_workspace_id or DEV_WORKSPACE_ID

    # CLI / server-to-server API key bypasses Clerk
    if x_api_key and settings.cli_api_key and x_api_key == settings.cli_api_key:
        if not settings.cli_workspace_id:
            raise HTTPException(status_code=500, detail="CLI_WORKSPACE_ID is not configured on the server")
        return settings.cli_workspace_id

    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header required")

    claims = _verify_clerk_token(credentials.credentials)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = claims.get("sub")

    if x_workspace_id:
        # Validate the user actually belongs to the requested workspace
        _assert_workspace_member(db, x_workspace_id, user_id)
        return x_workspace_id

    workspace_id = claims.get("org_id") or claims.get("sub")
    if not workspace_id:
        raise HTTPException(status_code=401, detail="No workspace in token claims")

    return workspace_id


def get_user_workspace_role(
    user_id: Annotated[str, Depends(get_user_id)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    db: Session = Depends(get_db),
) -> str:
    """
    Returns the authenticated user's role in the requested workspace.
    Raises 403 if the user is not a member. Skips check in dev mode.
    """
    if not _clerk_enabled():
        return "admin"

    from sqlalchemy import text
    row = db.execute(
        text("SELECT role FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid"),
        {"ws": workspace_id, "uid": user_id},
    ).fetchone()

    if not row:
        # Legacy fallback: owner_id on workspaces table (pre-migration workspaces)
        owner_row = db.execute(
            text("SELECT owner_id FROM workspaces WHERE id = :ws AND owner_id = :uid"),
            {"ws": workspace_id, "uid": user_id},
        ).fetchone()
        if owner_row:
            return "admin"

        # Self-heal: if workspace_users is completely empty for this workspace
        # (e.g. after a DB truncate), grant the first authenticated user admin access
        # and insert them so subsequent requests are fast.
        member_count = db.execute(
            text("SELECT COUNT(*) FROM workspace_users WHERE workspace_id = :ws"),
            {"ws": workspace_id},
        ).scalar()
        if member_count == 0:
            from datetime import datetime, timezone
            db.execute(
                text("""
                    INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at)
                    VALUES (:ws, :uid, 'admin', :now)
                    ON CONFLICT DO NOTHING
                """),
                {"ws": workspace_id, "uid": user_id, "now": datetime.now(timezone.utc)},
            )
            db.commit()
            return "admin"

        raise HTTPException(status_code=403, detail="Not a member of this workspace")

    return row.role


def require_workspace_role(*allowed_roles: str):
    """
    Dependency factory that enforces minimum role for an endpoint.

    Usage:
        @router.post("/members")
        def add_member(_: str = Depends(require_workspace_role("admin")), ...):
    """
    def _check(role: Annotated[str, Depends(get_user_workspace_role)]) -> str:
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Requires role: {', '.join(allowed_roles)}")
        return role
    return _check
