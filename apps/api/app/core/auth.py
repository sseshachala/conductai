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
import structlog
import threading
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db

log = structlog.get_logger(__name__)

DEV_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
DEV_USER_ID = "dev"

_bearer = HTTPBearer(auto_error=False)

_jwks_cache: dict | None = None
_jwks_lock = threading.Lock()


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
    with _jwks_lock:
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
        clerk_domain = settings.clerk_frontend_api or ""
        expected_issuer = f"https://{clerk_domain}" if clerk_domain else None
        audience = settings.clerk_audience or None
        decode_options: dict = {}
        if not audience:
            decode_options["verify_aud"] = False
        decode_kwargs: dict = {}
        if expected_issuer:
            decode_kwargs["issuer"] = expected_issuer
        else:
            decode_options["verify_iss"] = False
        if audience:
            decode_kwargs["audience"] = audience
        claims = pyjwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            options=decode_options,
            leeway=30,
            **decode_kwargs,
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


def get_clerk_user_info(user_id: str) -> dict:
    """Return {email, name} for a Clerk user. Falls back to empty strings on failure."""
    if not settings.clerk_secret_key or not user_id:
        return {"email": None, "name": None}
    try:
        r = httpx.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
            timeout=5,
        )
        if not r.is_success:
            return {"email": None, "name": None}
        data = r.json()
        primary_id = data.get("primary_email_address_id")
        email = None
        for e in data.get("email_addresses", []):
            if e.get("id") == primary_id:
                email = e.get("email_address")
                break
        if not email:
            emails = data.get("email_addresses", [])
            email = emails[0].get("email_address") if emails else None
        first = data.get("first_name") or ""
        last = data.get("last_name") or ""
        name = f"{first} {last}".strip() or None
        return {"email": email, "name": name}
    except Exception as e:
        log.warning("Could not fetch Clerk user info for %s: %s", user_id, e)
        return {"email": None, "name": None}


def get_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    x_api_key: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> str:
    """Returns the Clerk user_id (sub claim), or 'dev' in local dev mode."""
    if not _clerk_enabled():
        return DEV_USER_ID

    # Master API key — return synthetic user ID scoped to the CLI workspace
    if x_api_key and settings.cli_api_key and x_api_key == settings.cli_api_key:
        return f"api-key:{settings.cli_workspace_id}"

    # Per-user cond_live_ key — return the stored user_id
    if x_api_key and x_api_key.startswith("cond_live_"):
        import hashlib
        from app.models.conduct_api_key import ConductApiKey
        key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
        row = db.query(ConductApiKey).filter(ConductApiKey.key_hash == key_hash).first()
        if row:
            return row.user_id
        raise HTTPException(status_code=401, detail="Invalid API key")

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
    import re as _re
    if not _re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", workspace_id, _re.I):
        raise HTTPException(status_code=403, detail="Invalid workspace ID — please select a workspace")
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

    # Master server-to-server key (env var) — unchanged
    if x_api_key and settings.cli_api_key and x_api_key == settings.cli_api_key:
        if not settings.cli_workspace_id:
            raise HTTPException(status_code=500, detail="CLI_WORKSPACE_ID is not configured on the server")
        return settings.cli_workspace_id

    # Per-user CONDUCT_API_KEY (cond_live_...) — verified against DB hash
    if x_api_key and x_api_key.startswith("cond_live_"):
        import hashlib
        from app.models.conduct_api_key import ConductApiKey
        from datetime import datetime, timezone
        key_hash = hashlib.sha256(x_api_key.encode()).hexdigest()
        row = db.query(ConductApiKey).filter(ConductApiKey.key_hash == key_hash).first()
        if not row:
            raise HTTPException(status_code=401, detail="Invalid API key")
        if row.expires_at and row.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=401, detail="API key expired")
        # Update last_used_at async-style (best effort, don't block)
        try:
            row.last_used_at = datetime.now(timezone.utc)
            db.commit()
        except Exception:
            db.rollback()
        return row.workspace_id

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

    # workspace_id must be a valid UUID — Clerk user_ids (user_xxx) are not.
    # This happens when the client cookie holds a personal Clerk ID instead of an org UUID.
    import re as _re
    _UUID_RE = _re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", _re.I)
    if not _UUID_RE.match(workspace_id):
        raise HTTPException(status_code=403, detail="Invalid workspace ID — please select a workspace")

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
        # (e.g. after a DB truncate in local dev), grant the first authenticated user
        # admin access and insert them so subsequent requests are fast.
        # Disabled in production — an empty workspace there means misconfiguration,
        # not a recovery scenario. Granting access silently would be a privilege escalation.
        if settings.environment == "production":
            raise HTTPException(status_code=403, detail="Not a member of this workspace")

        member_count = db.execute(
            text("SELECT COUNT(*) FROM workspace_users WHERE workspace_id = :ws"),
            {"ws": workspace_id},
        ).scalar()
        if member_count == 0:
            from datetime import datetime, timezone
            log.warning(
                "auth.self_heal_admin",
                workspace_id=workspace_id,
                user_id=user_id,
                note="workspace_users empty — granting first user admin (dev only)",
            )
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


def audit(
    db,
    workspace_id: str,
    action: str,
    *,
    actor_id: str | None = None,
    actor_email: str | None = None,
    actor_role: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Write one audit_log row. Fire-and-forget — never raises."""
    try:
        from app.models.audit_log import AuditLog
        db.add(AuditLog(
            workspace_id=workspace_id,
            actor_id=actor_id,
            actor_email=actor_email,
            actor_role=actor_role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            meta=metadata,
        ))
        db.commit()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


def get_guard_org_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> str:
    """Extract org/user ID from Clerk token for Guard endpoints. No workspace UUID required."""
    if not _clerk_enabled():
        return "dev-org"
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")
    claims = _verify_clerk_token(credentials.credentials)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    org_id = claims.get("org_id") or claims.get("sub")
    if not org_id:
        raise HTTPException(status_code=401, detail="No org_id in token")
    return org_id


def get_guard_hook_auth(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    db: Session = Depends(get_db),
) -> str:
    """Auth for hook/CLI endpoints that accept EITHER a Clerk JWT OR a member token.

    Returns org_id (from Clerk) or team_id string (from member token lookup).
    This allows `conduct guard sync` and the MCP server to call protected endpoints
    using the member_token issued at join time.
    """
    if not _clerk_enabled():
        return "dev-org"
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials

    # Try Clerk JWT first
    claims = _verify_clerk_token(token)
    if claims:
        org_id = claims.get("org_id") or claims.get("sub")
        if org_id:
            return org_id

    # Fall back to member token lookup
    from app.modules.guard.models import GuardMember
    member = db.query(GuardMember).filter(GuardMember.member_token == token).first()
    if member:
        return str(member.team_id)

    raise HTTPException(status_code=401, detail="Invalid or expired token")


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
