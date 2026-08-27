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
import contextvars
import structlog
import threading
from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import Depends, Header, HTTPException, Query
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

# Per-request dedupe for Okta audit emissions. FastAPI runs each request in a
# fresh async context, so this ContextVar naturally resets between requests.
# Same token resolved twice in one request → one audit row, not two (fixes
# the /auth/whoami double-emit).
_okta_audit_emitted: contextvars.ContextVar[set[str] | None] = contextvars.ContextVar(
    "okta_audit_emitted", default=None,
)

# ponytail: shared client — connection pooling, avoids per-call TLS handshake
_clerk_http = httpx.Client(timeout=5)


def _fetch_jwks() -> dict:
    clerk_domain = settings.clerk_frontend_api or ""
    if not clerk_domain:
        return {}
    try:
        r = httpx.get(f"https://{clerk_domain}/.well-known/jwks.json", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        log.warning("clerk.jwks_fetch_failed", error=str(e))
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
            log.warning("clerk.jwks_kid_not_found", kid=key_id)
            return None

        public_key = RSAAlgorithm.from_jwk(key)
        clerk_domain = settings.clerk_frontend_api or ""
        expected_issuer = f"https://{clerk_domain}" if clerk_domain else None
        audience = settings.clerk_audience or None
        # Security: if CLERK_AUDIENCE or CLERK_FRONTEND_API are unset, audience/issuer
        # verification is skipped — any valid Clerk JWT from any app will authenticate.
        # Set both env vars in production. Startup warnings are emitted by config.py.
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
        log.warning("clerk.token_verification_failed", error=str(e))
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
        r = _clerk_http.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
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
        log.warning("clerk.user_email_fetch_failed", user_id=user_id, error=str(e))
        return None


@lru_cache(maxsize=512)
def find_clerk_user_id_by_email(email: str) -> str | None:
    """Return the Clerk user_id for the given email, or None if not found."""
    if not settings.clerk_secret_key or not email:
        return None
    try:
        r = _clerk_http.get(
            "https://api.clerk.com/v1/users",
            params={"email_address": email, "limit": 1},
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
        )
        if not r.is_success:
            return None
        users = r.json()
        return users[0]["id"] if users else None
    except Exception as e:
        log.warning("clerk.user_search_by_email_failed", email=email, error=str(e))
        return None


@lru_cache(maxsize=512)
def get_clerk_user_info(user_id: str) -> dict:
    """Return {email, name} for a Clerk user. Falls back to empty strings on failure."""
    if not settings.clerk_secret_key or not user_id:
        return {"email": None, "name": None}
    try:
        r = _clerk_http.get(
            f"https://api.clerk.com/v1/users/{user_id}",
            headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
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
        log.warning("clerk.user_info_fetch_failed", user_id=user_id, error=str(e))
        return {"email": None, "name": None}


def _resolve_agent_token(token: str, db: Session):
    """Validate a cond_agt_* or cond_api_* token and return (AgentIdentity, clerk_user_id).
    Raises HTTPException on invalid/expired token or missing GMC link.
    For api tokens (token_type='api') there is no GMC link by design — returns (ai, None).
    Shared by get_workspace_id, get_user_id, get_guard_hook_auth to avoid double-decrypt.
    """
    from app.modules.agent_identity.models import AgentIdentity
    from app.core.crypto import decrypt
    from sqlalchemy import text as _t
    from datetime import datetime, timezone as _tz
    for ai in db.query(AgentIdentity).filter(AgentIdentity.token_prefix == token[:13]).all():
        try:
            if decrypt(ai.token_encrypted).get("token") == token:
                if ai.expires_at and ai.expires_at < datetime.now(_tz.utc):
                    raise HTTPException(status_code=401, detail="Agent token expired — run `conduct login`")
                # Fail-secure lifecycle guard (#1037). Deactivated/expired
                # identities cannot authenticate even if their token has not
                # expired. Applies to cond_agt_*, cond_api_*, and legacy paths.
                _lifecycle = getattr(ai, "lifecycle_state", None)
                if _lifecycle in ("deactivated", "expired"):
                    raise HTTPException(status_code=401, detail=f"Agent identity is {_lifecycle}")
                # External identities (Okta-imported, etc.) authenticate via
                # their source system, never through Conduct's token path.
                # #1036 defense-in-depth against auth confusion.
                if getattr(ai, "token_type", "cli") == "external":
                    raise HTTPException(status_code=401, detail="External agent identity cannot authenticate via Conduct token path")
                # api tokens have no guard_member_config row by design
                if getattr(ai, 'token_type', 'cli') == 'api':
                    return ai, None
                row = db.execute(
                    _t("SELECT clerk_user_id FROM guard_member_config WHERE agent_identity_id = :aid LIMIT 1"),
                    {"aid": ai.id},
                ).fetchone()
                clerk_user_id = row.clerk_user_id if row else None
                return ai, clerk_user_id
        except HTTPException:
            raise
        except Exception:
            continue
    raise HTTPException(status_code=401, detail="Invalid agent token")


def _resolve_okta_jwt(token: str, db: Session):
    """Try to resolve `token` as an Okta-signed JWT (#1056).

    Returns (AgentIdentity, None) on success, matching the shape of
    `_resolve_agent_token(cond_api_*, ...)`. Returns None if the token is not
    a JWT or its `iss` is not configured for any workspace with
    `okta_auth_enabled=true` — the caller falls through to the next auth path
    (Clerk). Any real verification failure raises HTTPException(401).
    """
    if token.count(".") != 2:
        return None

    from app.core.okta_jwt import OktaJWTError, verify_okta_jwt
    from app.models.integration import Integration
    from app.modules.agent_identity.models import AgentIdentity
    import jwt as _pyjwt

    try:
        unverified = _pyjwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": False,
                "verify_aud": False,
                "verify_iss": False,
            },
        )
    except Exception:
        return None
    iss = unverified.get("iss")
    if not iss:
        return None

    # ponytail: one indexed lookup per non-cond_ request. Add a global
    # "any-okta-enabled" cache if this shows up in flame graphs.
    rows = (
        db.query(Integration)
        .filter(
            Integration.handle == "okta",
            Integration.okta_issuer == iss,
            Integration.okta_auth_enabled.is_(True),
        )
        .all()
    )
    if not rows:
        return None  # unconfigured issuer — fall through to Clerk

    # #1057 — hash-chained audit event for every verify attempt. Wrapped in
    # try/except so audit failures never break auth.
    import time as _time
    _t0 = _time.perf_counter()
    unverified_sub = unverified.get("sub", "")

    def _emit_audit(*, workspace_id, decision: str, sub: str, reason: str | None = None):
        # Per-request dedupe: if the same (workspace, decision, sub) was already
        # audited in this request, skip. See _okta_audit_emitted.
        _seen = _okta_audit_emitted.get()
        if _seen is None:
            _seen = set()
            _okta_audit_emitted.set(_seen)
        _key = f"{workspace_id}|{decision}|{sub}"
        if _key in _seen:
            return
        _seen.add(_key)
        try:
            from app.modules.guard.models import GuardAuditEvent, chain_hash_for_insert
            from datetime import datetime, timezone as _tz
            _now = datetime.now(_tz.utc)
            _tool = "auth.okta_jwt.verify"
            prev_hash, entry_hash = chain_hash_for_insert(db, workspace_id, _now, _tool, decision)
            db.add(GuardAuditEvent(
                workspace_id=workspace_id,
                user_email=sub or "unknown",
                ai_tool="okta_jwt",
                tool_call=_tool,
                source="okta_jwt",
                input_summary=f"iss={iss}",
                decision=decision,
                rule_id="okta_jwt",
                rule_message=reason,
                ts=_now,
                duration_ms=int((_time.perf_counter() - _t0) * 1000),
                previous_hash=prev_hash,
                entry_hash=entry_hash,
            ))
            db.commit()
        except Exception as _e:  # never let audit break auth
            log.warning("okta.audit.emit_failed", error=str(_e))
            try:
                db.rollback()
            except Exception:
                pass

    last_error: Exception | None = None
    for row in rows:
        aud = row.okta_audience or ""
        try:
            claims = verify_okta_jwt(token, issuer=iss, audience=aud)
        except OktaJWTError as e:
            last_error = e
            continue
        sub = claims.get("sub")
        if not sub:
            _emit_audit(workspace_id=row.workspace_id, decision="blocked", sub=unverified_sub, reason="missing sub claim")
            raise HTTPException(status_code=401, detail="Okta JWT missing sub claim")
        ai = (
            db.query(AgentIdentity)
            .filter(
                AgentIdentity.workspace_id == row.workspace_id,
                AgentIdentity.source == "okta",
                AgentIdentity.source_id == sub,
            )
            .first()
        )
        if not ai:
            _emit_audit(workspace_id=row.workspace_id, decision="blocked", sub=sub, reason="identity not synced")
            raise HTTPException(status_code=401, detail="Okta identity not synced — run Okta sync in Conduct")
        lifecycle = getattr(ai, "lifecycle_state", None)
        if lifecycle in ("deactivated", "expired"):
            _emit_audit(workspace_id=row.workspace_id, decision="blocked", sub=sub, reason=f"lifecycle={lifecycle}")
            raise HTTPException(status_code=401, detail=f"Agent identity is {lifecycle}")
        _emit_audit(workspace_id=row.workspace_id, decision="allowed", sub=sub)
        return ai, None

    # All configured workspaces rejected the token
    _emit_audit(workspace_id=rows[0].workspace_id, decision="blocked", sub=unverified_sub, reason=str(last_error))
    raise HTTPException(status_code=401, detail=f"Okta JWT verification failed: {last_error}")


def get_user_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
    db: Session = Depends(get_db),
) -> str | None:
    """Returns the Clerk user_id (sub claim), 'dev' in local dev mode, or None for machine API tokens."""
    if not globals()["_clerk_enabled"]():
        return DEV_USER_ID

    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header required")

    # cond_agt_* / cond_api_* — look up clerk_user_id via guard_member_config FK
    if credentials.credentials.startswith(("cond_agt_", "cond_api_")):
        ai, clerk_user_id = _resolve_agent_token(credentials.credentials, db)
        if not clerk_user_id:
            if getattr(ai, 'token_type', 'cli') == 'api':
                return None  # machine identity — no user session
            raise HTTPException(status_code=401, detail="Agent token not linked to a user — re-run `conduct login`")
        return clerk_user_id

    # Okta JWT (#1056) — machine identities, no user session (like cond_api_*)
    if _resolve_okta_jwt(credentials.credentials, db) is not None:
        return None

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
    ws_id: Annotated[str | None, Query(alias="workspace_id")] = None,
    x_workspace_id: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> str:
    """
    Returns the active workspace/project ID for the request.

    Resolution order:
    1. ?workspace_id= query param (explicit — preferred)
    2. X-Workspace-Id header (backward compat)
    3. Bearer token (cond_run_* / cond_agt_* / cond_api_* / Clerk JWT)
    4. Dev workspace (when Clerk is not configured)
    """
    explicit_ws = ws_id or x_workspace_id
    if not globals()["_clerk_enabled"]():
        return explicit_ws or DEV_WORKSPACE_ID

    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header required")

    # run_token (cond_run_*) — short-lived per-run token, validated by hash
    if credentials.credentials.startswith("cond_run_"):
        import hashlib as _h
        from app.modules.agent_identity.run_token_model import AgentRunToken as _ART
        _hash = _h.sha256(credentials.credentials.encode()).hexdigest()
        _rt = db.query(_ART).filter(_ART.token_hash == _hash, _ART.invalidated_at.is_(None)).first()
        if not _rt:
            raise HTTPException(status_code=401, detail="Invalid or expired run token")
        token_ws = str(_rt.workspace_id)
        if explicit_ws and explicit_ws != token_ws:
            raise HTTPException(status_code=403, detail="Run token does not belong to the requested workspace")
        return explicit_ws or token_ws

    # agent_token (cond_agt_* / cond_api_*) — look up in agent_identities
    if credentials.credentials.startswith(("cond_agt_", "cond_api_")):
        ai, _ = _resolve_agent_token(credentials.credentials, db)
        token_ws = str(ai.workspace_id)
        if explicit_ws and explicit_ws != token_ws:
            raise HTTPException(status_code=403, detail="Agent token does not belong to the requested workspace")
        return explicit_ws or token_ws

    # Okta JWT (#1056) — resolves before Clerk. Returns None for tokens whose
    # issuer isn't configured, so Clerk JWTs still work.
    okta = _resolve_okta_jwt(credentials.credentials, db)
    if okta is not None:
        ai, _ = okta
        token_ws = str(ai.workspace_id)
        if explicit_ws and explicit_ws != token_ws:
            raise HTTPException(status_code=403, detail="Okta JWT does not belong to the requested workspace")
        return explicit_ws or token_ws

    claims = _verify_clerk_token(credentials.credentials)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = claims.get("sub")

    if explicit_ws:
        # Validate the user actually belongs to the requested workspace
        _assert_workspace_member(db, explicit_ws, user_id)
        return explicit_ws

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
    if not globals()["_clerk_enabled"]():
        return "admin"

    # workspace_id must be a valid UUID — Clerk user_ids (user_xxx) are not.
    # This happens when the client cookie holds a personal Clerk ID instead of an org UUID.
    import uuid as _uuid
    try:
        _uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid workspace ID — please select a workspace")

    from sqlalchemy import text
    row = db.execute(
        text("SELECT role FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid"),
        {"ws": workspace_id, "uid": user_id},
    ).fetchone()

    if not row:
        # Workspace owner still gets admin (the create-workspace webhook inserts
        # both owner_id and workspace_users; the owner_id path covers legacy or
        # truncated-in-dev workspaces where the membership row is missing).
        owner_row = db.execute(
            text("SELECT owner_id FROM workspaces WHERE id = :ws AND owner_id = :uid"),
            {"ws": workspace_id, "uid": user_id},
        ).fetchone()
        if owner_row:
            return "admin"
        # Any other caller into a workspace they don't own = cross-tenant probe.
        # The old "empty workspace → grant first user admin" self-heal was a
        # dev-only escalation that let isolation tests pass in CI. Removed.
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
    """Extract org/user ID for Guard endpoints.

    Accepts: Clerk Bearer JWT — returns org_id or sub claim.
    """
    if not globals()["_clerk_enabled"]():
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
    """Auth for hook/CLI endpoints. Accepts cond_agt_* agent token or Clerk JWT."""
    if not globals()["_clerk_enabled"]():
        return "dev-org"

    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials

    # cond_agt_* / cond_api_* agent token
    if token.startswith(("cond_agt_", "cond_api_")):
        ai, _ = _resolve_agent_token(token, db)
        return str(ai.workspace_id)

    # Okta JWT (#1056) — resolves before Clerk. Returns None for tokens whose
    # issuer isn't configured, so Clerk JWTs still work.
    okta = _resolve_okta_jwt(token, db)
    if okta is not None:
        ai, _ = okta
        return str(ai.workspace_id)

    # Clerk JWT
    claims = _verify_clerk_token(token)
    if claims:
        org_id = claims.get("org_id") or claims.get("sub")
        if org_id:
            return org_id

    raise HTTPException(status_code=401, detail="Invalid or expired token")


def get_valid_roles(db: Session) -> set[str]:
    """Return system role names from the DB. Falls back to the 4 canonical names if tables are empty."""
    from sqlalchemy import text as _text
    rows = db.execute(
        _text("SELECT name FROM roles WHERE workspace_id IS NULL"),
    ).fetchall()
    if rows:
        return {r.name for r in rows}
    return {"admin", "developer", "security", "viewer"}


def get_role_description(role: str, db: Session) -> str:
    """Return the description for a role from the DB."""
    from sqlalchemy import text as _text
    row = db.execute(
        _text("SELECT description FROM roles WHERE name = :name AND workspace_id IS NULL"),
        {"name": role},
    ).fetchone()
    return row.description if row and row.description else ""


def require_workspace_role(*allowed_roles: str):
    """
    Dependency factory that enforces minimum role for an endpoint.

    Usage:
        @router.post("/members")
        def add_member(_: str = Depends(require_workspace_role("admin")), ...):

    Prefer require_permission() for all new endpoints — it checks via the
    DB-seeded RBAC tables instead of hardcoded role name lists.
    """
    def _check(role: Annotated[str, Depends(get_user_workspace_role)]) -> str:
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Requires role: {', '.join(allowed_roles)}")
        return role
    return _check


def check_permission(
    *,
    user_id: str | None,
    workspace_id: str,
    credentials: HTTPAuthorizationCredentials | None,
    db: Session,
    permission: str,
) -> str:
    """Pure permission check. No FastAPI DI, no closures over factory args.

    Returns the effective role on success. Raises HTTPException(403) on failure.

    Callable directly from unit tests: pass a mocked db (or a real one) and a
    workspace/user pair; get the same behavior FastAPI routes get. Patch
    _clerk_enabled at the module level to simulate the dev-bypass path.

    See require_permission() below for the FastAPI wrapper used by routers.
    """
    from sqlalchemy import text as _text

    # Use an explicit dict lookup so that unittest.mock.patch reliably replaces
    # _clerk_enabled at test time.  Python 3.11's LOAD_GLOBAL inline cache can
    # serve a stale pointer to the original function even after setattr() updates
    # the module __dict__; going through globals() forces a fresh dict read.
    if not globals()["_clerk_enabled"]():
        return "admin"

    import re as _re
    if not _re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", workspace_id, _re.I):
        raise HTTPException(status_code=403, detail="Invalid workspace ID")

    # Machine tokens (cond_api_*) are workspace-scoped credentials with no
    # user session. Treat as admin for the workspace they were minted for.
    # Same model as AWS access keys, GitHub PATs, Stripe secret keys —
    # the token IS the authorization.
    if user_id is None and credentials and credentials.credentials.startswith("cond_api_"):
        ai, _ = _resolve_agent_token(credentials.credentials, db)
        if ai and str(getattr(ai, "workspace_id", "")) == workspace_id:
            return "admin"
        raise HTTPException(status_code=403, detail="API token workspace does not match request")

    # Okta JWTs (#1056) are also workspace-scoped machine credentials —
    # user_id is None because get_user_id returned None for the JWT above.
    if user_id is None and credentials:
        okta = _resolve_okta_jwt(credentials.credentials, db)
        if okta is not None:
            ai, _ = okta
            if str(getattr(ai, "workspace_id", "")) == workspace_id:
                return "admin"
            raise HTTPException(status_code=403, detail="Okta JWT workspace does not match request")

    row = db.execute(
        _text("SELECT role FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid"),
        {"ws": workspace_id, "uid": user_id},
    ).fetchone()

    if not row:
        owner = db.execute(
            _text("SELECT 1 FROM workspaces WHERE id = :ws AND owner_id = :uid"),
            {"ws": workspace_id, "uid": user_id},
        ).fetchone()
        if owner:
            return "admin"
        # GMC fallback: cond_agt_* tokens prove authenticated workspace membership
        gmc = db.execute(
            _text("""
                SELECT 1 FROM guard_member_config
                WHERE workspace_id::text = :ws AND clerk_user_id = :uid
                LIMIT 1
            """),
            {"ws": workspace_id, "uid": user_id},
        ).fetchone()
        if gmc:
            return "admin"
        raise HTTPException(status_code=403, detail="Not a member of this workspace")

    user_role = row.role

    has_perm = db.execute(
        _text("""
            SELECT 1
            FROM roles r
            JOIN role_permissions rp ON rp.role_id = r.id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE r.name = :role
              AND r.workspace_id IS NULL
              AND p.name = :perm
            LIMIT 1
        """),
        {"role": user_role, "perm": permission},
    ).fetchone()

    if not has_perm:
        # Fallback: if the RBAC tables are unseeded (migration 0044 not yet
        # applied), grant access based on role tier so no env gets locked out.
        seeded = db.execute(
            _text("SELECT 1 FROM role_permissions LIMIT 1"),
        ).fetchone()
        if not seeded:
            # Tables empty — derive access from role tier (mirrors the old
            # require_workspace_role logic): admin=all, viewer=read-only,
            # developer+security=read+write (conservative safe default).
            read_only_perms = {
                "platform.workflows.view", "platform.runs.view",
                "platform.marketplace.browse", "platform.eval.view",
                "guard.policies.view", "guard.activity.view_own",
                "guard.spend.view_own",
            }
            if user_role == "admin":
                return user_role
            if user_role in ("developer", "security") and permission in read_only_perms:
                return user_role
            if user_role == "viewer" and permission in read_only_perms:
                return user_role
            # Write permissions need at least developer/security
            if user_role in ("developer", "security"):
                return user_role
        raise HTTPException(status_code=403, detail=f"Permission denied: {permission}")

    return user_role


def require_permission(permission: str):
    """FastAPI dependency factory. Thin wrapper around check_permission().

    The check logic lives in check_permission() (pure function, unit-testable
    without conftest-patch acrobatics). This wrapper only binds FastAPI DI to
    that function so routers can use ``Depends(require_permission("perm.name"))``.

    Seeded permissions (from migration 0044):
      platform.workflows.view       — viewer, developer, security, admin
      platform.workflows.edit       — developer, admin
      platform.workflows.run        — developer, admin
      platform.runs.view            — viewer, developer, security, admin
      platform.marketplace.browse   — viewer, developer, security, admin
      platform.marketplace.install  — developer, admin
      platform.eval.view            — viewer, developer, security, admin
      platform.workspace.edit       — admin
      platform.members.manage       — admin
      platform.credentials.manage   — developer, security, admin
      platform.audit_log.view       — security, admin
      guard.activity.view_all       — security, admin
      guard.activity.view_own       — developer, security, admin (own only)
      guard.activity.export         — security, admin
      guard.spend.view_all          — security, admin
      guard.spend.view_own          — developer, security, admin (own only)
      guard.spend.budgets.edit      — admin
      guard.policies.view           — viewer, developer, security, admin
      guard.policies.edit           — security, admin
      guard.settings.edit           — admin

    Usage:
        @router.get("/scorecards")
        def get_scorecards(_: str = Depends(require_permission("platform.eval.view")), ...):
    """
    def _check(
        user_id: Annotated[str | None, Depends(get_user_id)],
        workspace_id: Annotated[str, Depends(get_workspace_id)],
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
        db: Session = Depends(get_db),
    ) -> str:
        return check_permission(
            user_id=user_id,
            workspace_id=workspace_id,
            credentials=credentials,
            db=db,
            permission=permission,
        )
    return _check


# ─── Shared agent token resolver ──────────────────────────────────────────────

_AGENT_PREFIX  = "cond_agt_"
_API_PREFIX    = "cond_api_"
_MEMBER_PREFIX = "guard-mt-"
_PREFIX_LOOKUP_LEN = len(_AGENT_PREFIX) + 4  # same length for all conduct token types


def resolve_agent_token(token: str, db: Session) -> tuple[str, str] | None:
    """Resolve any Conduct agent token → (workspace_id, clerk_user_id) or None.

    Accepts: cond_agt_*, cond_api_*, guard-mt-* (legacy member tokens).
    Used by proxy, MCP, WebSocket, and any other auth surface.

    Fail-secure: expired tokens return None. Callers that need to distinguish
    "expired" from "unknown" (e.g. proxy UX copy) can call token_is_expired()
    on the same token to disambiguate before rendering the error message.
    """
    from sqlalchemy import text as _text
    from datetime import datetime, timezone as _tz

    if token.startswith((_AGENT_PREFIX, _API_PREFIX)):
        from app.core.crypto import decrypt as _decrypt
        from app.modules.agent_identity.models import AgentIdentity

        prefix = token[:_PREFIX_LOOKUP_LEN]
        for ai_row in db.query(AgentIdentity).filter(AgentIdentity.token_prefix == prefix).all():
            try:
                if _decrypt(ai_row.token_encrypted).get("token") != token:
                    continue
            except Exception:
                continue

            # Reject expired session tokens (cond_agt_ has 8h TTL). API tokens
            # (cond_api_) leave expires_at=NULL by design, so this only bites
            # session tokens.
            if ai_row.expires_at and ai_row.expires_at < datetime.now(_tz.utc):
                return None

            # Fail-secure on identity lifecycle state (#1037).
            # deactivated or expired identities cannot authenticate regardless
            # of token freshness. pending_review is a signal, not a stop.
            _lifecycle = getattr(ai_row, "lifecycle_state", None)
            if _lifecycle in ("deactivated", "expired"):
                return None

            # Try guard_member_config link first (session tokens always have this)
            member = db.execute(
                _text("""
                    SELECT workspace_id::text, clerk_user_id
                    FROM guard_member_config
                    WHERE agent_identity_id = :aid AND active = true
                    LIMIT 1
                """),
                {"aid": ai_row.id},
            ).fetchone()
            if member:
                return (member[0], member[1])

            # API tokens: fall back to creator or synthetic label
            creator = getattr(ai_row, "created_by_clerk_user_id", None)
            if creator:
                return (str(ai_row.workspace_id), creator)

            label = getattr(ai_row, "token_name", None) or getattr(ai_row, "name", "api-token")
            return (str(ai_row.workspace_id), f"api:{label}")

        return None

    # Legacy guard-mt-* member token
    bare = token[len(_MEMBER_PREFIX):] if token.startswith(_MEMBER_PREFIX) else token
    row = db.execute(
        _text("""
            SELECT workspace_id::text, clerk_user_id
            FROM guard_member_config
            WHERE member_token = :tok AND active = true
            LIMIT 1
        """),
        {"tok": bare},
    ).fetchone()
    return (row[0], row[1]) if row else None


def token_is_expired(token: str, db: Session) -> bool:
    """True iff token matches a real AgentIdentity row whose expires_at has passed.

    Used by proxy 401 handler to render "session expired — run conduct login"
    instead of the generic "not recognized" message. Cheap: one indexed lookup
    on token_prefix, decrypt only the prefix-collision matches.
    """
    if not token.startswith((_AGENT_PREFIX, _API_PREFIX)):
        return False
    from datetime import datetime, timezone as _tz
    from app.core.crypto import decrypt as _decrypt
    from app.modules.agent_identity.models import AgentIdentity

    prefix = token[:_PREFIX_LOOKUP_LEN]
    for ai_row in db.query(AgentIdentity).filter(AgentIdentity.token_prefix == prefix).all():
        try:
            if _decrypt(ai_row.token_encrypted).get("token") != token:
                continue
        except Exception:
            continue
        return bool(ai_row.expires_at and ai_row.expires_at < datetime.now(_tz.utc))
    return False
