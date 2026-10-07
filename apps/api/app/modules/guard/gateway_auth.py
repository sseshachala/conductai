"""Gateway request-path auth: ``GatewayAuth`` resolution and the member-token auth-cache fetch.

Split out of ``gateway_helpers``; re-exported there so existing imports keep working."""

from __future__ import annotations

from dataclasses import dataclass
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session


@dataclass
class GatewayAuth:
    """Resolved auth for a gateway request. Extracted from
    ``handle_gateway_request`` so admission can wrap the whole post-auth
    body cleanly."""
    workspace_id: str
    clerk_user_id: str
    is_internal: bool
    agent_identity_id: str | None = None
    agent_risk_tier: str | None = None
    token: str = ""


def _resolve_gateway_auth(
    request: Request,
    *,
    token: str | None,
    internal_key: str,
    needs_run_token_validation: bool,
    needs_agent_validation: bool,
) -> "GatewayAuth | JSONResponse":
    """Resolves auth for a gateway request. Owns its own DB session — opens
    at entry, closes in a finally regardless of exit path. Callers invoke
    via ``run_in_threadpool`` so the event loop is not blocked during
    the sync SQLAlchemy work.

    Returns ``GatewayAuth`` on success. Returns a ``JSONResponse`` when
    auth fails (401/400).
    """
    from app.core.database import SessionLocal as _SessionLocal
    db = _SessionLocal()
    try:
        return _resolve_gateway_auth_inner(
            request, db,
            token=token,
            internal_key=internal_key,
            needs_run_token_validation=needs_run_token_validation,
            needs_agent_validation=needs_agent_validation,
        )
    finally:
        db.close()


def _resolve_gateway_auth_inner(
    request: Request,
    db: Session,
    *,
    token: str | None,
    internal_key: str,
    needs_run_token_validation: bool,
    needs_agent_validation: bool,
) -> "GatewayAuth | JSONResponse":
    """Auth resolution implementation. Uses caller-provided db. Kept as a
    separate function so the session-owning wrapper stays a thin
    open/close shell."""
    import hashlib as _hashlib
    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz

    from app.core.auth import (
        resolve_agent_token,
        token_is_expired,
        _resolve_agent_token as _resolve_ai,
        resolve_agent_identity_row as _rair,
    )
    from app.core.workspace_context import set_workspace_rls
    from app.guard.router import fail_closed as _fail_closed
    from app.modules.agent_identity.models import AgentIdentity as _AgentIdentity
    from app.modules.agent_identity.run_token_model import AgentRunToken as _AgentRunToken
    from fastapi import HTTPException as _HTTPException

    is_internal = False
    agent_identity_id: str | None = None
    agent_risk_tier: str | None = None
    workspace_id = ""
    clerk_user_id = ""

    if needs_run_token_validation:
        _hdr_ws = request.headers.get("x-conductai-workspace-id", "")
        if not _hdr_ws:
            return _fail_closed(400, "X-Conductai-Workspace-Id required for run token calls")
        _token_hash = _hashlib.sha256(internal_key.encode()).hexdigest()
        _now_rt = _dt.now(_tz.utc)
        _rt = db.query(_AgentRunToken).filter(
            _AgentRunToken.token_hash == _token_hash,
            _AgentRunToken.workspace_id == _uuid.UUID(_hdr_ws),
            _AgentRunToken.invalidated_at == None,  # noqa: E711
            _AgentRunToken.expires_at > _now_rt,
        ).first()
        if not _rt:
            return _fail_closed(401, "Run token not found, expired, or already invalidated")
        is_internal = True
        if not _rt.first_used_at:
            _rt.first_used_at = _now_rt
            db.commit()

    if needs_agent_validation and not is_internal:
        _hdr_ws = request.headers.get("x-conductai-workspace-id", "")
        if not _hdr_ws:
            return _fail_closed(400, "X-Conductai-Workspace-Id required for agent identity calls")
        try:
            _ai, _ = _resolve_ai(internal_key, db)
        except _HTTPException as _exc:
            return _fail_closed(int(_exc.status_code), str(_exc.detail or "Agent Identity token not recognized"))
        if str(_ai.workspace_id) != _hdr_ws:
            return _fail_closed(401, "Agent Identity token does not belong to the requested workspace")
        is_internal = True
        agent_identity_id = _ai.id
        agent_risk_tier = getattr(_ai, "risk_tier", None)

    if is_internal:
        workspace_id = request.headers.get("x-conductai-workspace-id", "")
        if not workspace_id:
            return _fail_closed(400, "X-Conductai-Workspace-Id required for internal proxy calls")
        set_workspace_rls(db, workspace_id)
        _internal_email = request.headers.get("x-conductai-user-email") or None
        clerk_user_id = _internal_email or "system"
        if agent_identity_id:
            _id_row = db.query(_AgentIdentity).filter(_AgentIdentity.id == agent_identity_id).first()
            if _id_row:
                _id_row.last_used_at = _dt.now(_tz.utc)
                db.commit()
    else:
        ident = resolve_agent_token(token, db)
        if not ident:
            if token_is_expired(token, db):
                return _fail_closed(401, "Conduct session expired — run `conduct login`")
            return _fail_closed(401, "Conduct member token not recognized — run `conduct login`")
        workspace_id, clerk_user_id = ident
        set_workspace_rls(db, workspace_id)
        try:
            _proxy_ai_row = _rair(token, db)
            if _proxy_ai_row:
                agent_risk_tier = getattr(_proxy_ai_row, "risk_tier", None)
                agent_identity_id = getattr(_proxy_ai_row, "id", None) or agent_identity_id
        except Exception:
            pass

    return GatewayAuth(
        workspace_id=workspace_id,
        clerk_user_id=clerk_user_id,
        is_internal=is_internal,
        agent_identity_id=agent_identity_id,
        agent_risk_tier=agent_risk_tier,
        token=token or "",
    )


# ── Auth cache fetch (PR 6b wiring) ──────────────────────────────────────────
#
# Async fetch function passed to ``init_auth_cache`` in main.py startup. Only
# covers the member-token branch (Clerk session tokens) — run tokens and
# agent identity tokens are one-shot verifications with per-request headers
# and are not cache-friendly.
#
# Runs the sync SQLAlchemy work in a threadpool so the event loop stays free.
async def auth_cache_fetch_member(token: str):
    """Resolve a member (Clerk) token to CachedAuth. Returns None if
    the token is unknown/invalid — AuthCache treats None as no-op."""
    from app.core.auth_cache import CachedAuth
    from app.core.database import SessionLocal as _SessionLocal
    from app.core.auth import resolve_agent_token, resolve_agent_identity_row
    from starlette.concurrency import run_in_threadpool

    def _fetch_sync():
        db = _SessionLocal()
        try:
            ident = resolve_agent_token(token, db)
            if not ident:
                return None
            workspace_id, clerk_user_id = ident
            agent_identity_id = None
            agent_risk_tier = None
            try:
                ai = resolve_agent_identity_row(token, db)
                if ai is not None:
                    _ai_id = getattr(ai, "id", None)
                    agent_identity_id = str(_ai_id) if _ai_id is not None else None
                    agent_risk_tier = getattr(ai, "risk_tier", None)
            except Exception:
                # Best-effort — a downstream lookup failure must not
                # invalidate an otherwise-valid session.
                pass
            return CachedAuth(
                workspace_id=str(workspace_id),
                clerk_user_id=clerk_user_id,
                agent_identity_id=agent_identity_id,
                agent_risk_tier=agent_risk_tier,
                is_internal=False,
                token_expires_at=None,
            )
        finally:
            db.close()

    return await run_in_threadpool(_fetch_sync)
