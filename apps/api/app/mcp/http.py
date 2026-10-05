"""HTTP adapter for MCPCore — #1219 Phase 3.

Mounts the transport-agnostic dispatcher at /mcp using JSON-RPC 2.0 over
HTTP. Handles Bearer auth, OAuth resource metadata (RFC 9728), and the
streamable HTTP Mcp-Session-Id header.

Once #1219 Phase 3b lands the tool registrations, this endpoint fully
replaces /guard/mcp. Until then, /mcp runs alongside and serves an empty
registry — useful for pattern verification but not yet a full replacement.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy.orm import Session

from starlette.concurrency import run_in_threadpool

from app.core.admission import AdmissionRefused, admission_refused_jsonrpc, admit
from app.core.database import get_db
from app.mcp import surface_session
from app.mcp.server import (
    MCPContext,
    _detect_surface,
    dispatch,
    new_session_id,
)
from app.tools.registry import default_registry

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/mcp", tags=["mcp"])


def _extract_bearer(request: Request) -> str | None:
    """Pull the raw Bearer token out of the Authorization header."""
    raw = request.headers.get("authorization", "")
    if raw.lower().startswith("bearer "):
        token = raw[7:].strip()
        return token or None
    return None


def _unauth_headers() -> dict[str, str]:
    from app.modules.auth.oauth.deployment import issuer_url
    issuer = issuer_url().rstrip("/")
    return {"WWW-Authenticate": (
        f'Bearer realm="{issuer}/mcp", '
        f'resource_metadata="{issuer}/.well-known/oauth-protected-resource/mcp"'
    )}


def _unauthorized(msg_id: Any = None, message: str = "missing token (use Authorization: Bearer)") -> JSONResponse:
    return JSONResponse(
        status_code=401,
        content={
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32600, "message": message},
        },
        headers=_unauth_headers(),
    )


def _auth_or_401(request: Request) -> tuple[str, str | None] | JSONResponse:
    """Resolve Bearer → (workspace_id, clerk_user_id) or return 401 JSONResponse."""
    token = _extract_bearer(request)
    if not token:
        return _unauthorized()
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        resolved = _resolve_workspace(token, db)
    finally:
        db.close()
    if resolved is None:
        return _unauthorized(message="Token not recognized")
    return resolved


def _resolve_workspace(token: str, db: Session) -> tuple[str, str | None] | None:
    """Look the token up in the agent-identity / member auth tables and
    return (workspace_id, clerk_user_id)."""
    try:
        from app.core.auth import resolve_agent_token
        ident = resolve_agent_token(token, db)
        if ident:
            workspace_id, clerk_user_id = ident
            return workspace_id, clerk_user_id
    except Exception as e:
        log.warning("mcp.http.token_resolve_failed", err=str(e))
    return None


@router.post("")
async def mcp_endpoint(request: Request) -> JSONResponse:
    """Handle one JSON-RPC 2.0 MCP request.

    - Missing Bearer → 401 with JSON-RPC error envelope
    - Body parse error → 400 with JSON-RPC error envelope
    - Notification (no id) → 204 no content
    - Otherwise → 200 with dispatch result + Mcp-Session-Id header
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error — request body is not valid JSON"},
            },
        )

    auth = _auth_or_401(request)
    if isinstance(auth, JSONResponse):
        return auth
    workspace_id, clerk_user_id = auth
    token = _extract_bearer(request) or ""
    from app.modules.auth.federation.mcp_ingress import prepare
    identity = await run_in_threadpool(prepare, request, workspace_id, token, body)
    if isinstance(identity, JSONResponse):
        return identity

    mcp_session_id = request.headers.get("mcp-session-id") or new_session_id()
    initializing = body.get("method") == "initialize"
    client_info = ((body.get("params") or {}).get("clientInfo") or {}) if initializing else {}
    reported_surface = _detect_surface(client_info)
    explicit_surface = _detect_surface({"name": request.headers.get("x-conduct-ai-tool", "")})
    initialized_session = (
        None if initializing else
        surface_session.resolve(mcp_session_id, workspace_id, clerk_user_id, token)
    )

    # Prefer the frontend identified at initialization over a shared backend's
    # legacy header or User-Agent. Every request still authenticates separately.
    surface = (
        (explicit_surface if explicit_surface != "unknown" else None)
        or (initialized_session.surface if initialized_session else None)
    )
    if not surface:
        surface = (
            (reported_surface if reported_surface != "unknown" else None)
            or request.headers.get("x-claude-surface")
        )
    if not surface:
        ua_surface = _detect_surface({"name": request.headers.get("User-Agent", "")})
        surface = ua_surface if ua_surface != "unknown" else "http"
    if initializing and surface in surface_session.SURFACES:
        mcp_session_id = surface_session.issue(surface, workspace_id, clerk_user_id, token)
        initialized_session = surface_session.resolve(mcp_session_id, workspace_id, clerk_user_id, token)

    # Guard tools need user_email + session_id for audit attribution and HITL
    # resume. Fetch email once per request; mint fresh session_id when the
    # client didn't provide one. (#1219 Phase 3b B2)
    user_email = None
    if clerk_user_id:
        try:
            from app.core.auth import get_clerk_user_email
            user_email = get_clerk_user_email(clerk_user_id) or clerk_user_id
        except Exception as e:
            log.warning("mcp.http.email_lookup_failed", err=str(e))
            user_email = clerk_user_id
    # Keep audit/approval correlation UUID-shaped; only the transport header
    # carries signed client metadata.
    session_id = request.headers.get("x-session-id") or (
        initialized_session.session_id if initialized_session else mcp_session_id
    )

    ctx = MCPContext(
        workspace_id=workspace_id,
        clerk_user_id=clerk_user_id,
        surface=surface,
        user_email=user_email,
        session_id=session_id,
        resolved_token=token,
        identity=identity,
    )

    try:
        async with admit("mcp", workspace_id):
            # ``dispatch`` is sync; ``run_in_threadpool`` offloads it so the
            # event loop stays free to admission-check other incoming requests
            # instead of serializing them behind this handler.
            response = await run_in_threadpool(dispatch, body, ctx, default_registry)
    except AdmissionRefused as e:
        return admission_refused_jsonrpc(body.get("id"), e)
    if response is None:
        # Notification (no id) — spec says 202/204 no body.
        # Use Response() not JSONResponse(content=None): the latter serializes
        # `null` (4 bytes) but sets Content-Length: 0, and uvicorn raises
        # RuntimeError("Response content longer than Content-Length") mid-send.
        # That truncated response is why Claude.ai's toolbox proxy returned 502.
        return Response(status_code=204)

    if initializing and isinstance(response.get("result"), dict):
        response["result"]["_surface"] = surface

    return JSONResponse(
        status_code=200,
        content=response,
        headers={"Mcp-Session-Id": mcp_session_id},
    )


@router.get("")
async def mcp_stream(request: Request) -> Response:
    """Optional server→client SSE stream (2025-06/08 streamable HTTP spec).

    Opens with one comment ping and idles; keepalives every 15s until the
    client disconnects. Stateless — no server-initiated notifications yet, but
    the endpoint exists so SDK clients that probe GET don't fail on 405.
    """
    auth = _auth_or_401(request)
    if isinstance(auth, JSONResponse):
        return auth

    async def _idle_stream():
        try:
            yield ": connected\n\n"
            while True:
                await asyncio.sleep(15)
                yield ": keepalive\n\n"
        except asyncio.CancelledError:
            return

    return StreamingResponse(
        _idle_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Render/Nginx buffer streaming responses by default; without this
            # header the client waits for first-byte until the reverse-proxy
            # timeout (typically 30s) and gets 502 Bad Gateway. Claude.ai's
            # toolbox proxy hit exactly that path — matches /guard/mcp SSE.
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("")
async def mcp_terminate(request: Request) -> Response:
    """Session termination (2025-06/08 spec).

    Stateless server → nothing to tear down; auth still required for parity.
    """
    auth = _auth_or_401(request)
    if isinstance(auth, JSONResponse):
        return auth
    return Response(status_code=204)


# ─── OAuth resource metadata (RFC 9728) ──────────────────────────────────────

well_known_router = APIRouter(tags=["mcp"])


@well_known_router.get("/.well-known/oauth-protected-resource/mcp")
async def oauth_resource_metadata() -> dict[str, Any]:
    """Advertised metadata for OAuth-capable MCP clients (Claude.ai etc).

    Same shape as /guard/mcp's existing well-known — points at the same
    authorization server. The resource URL changes to /mcp."""
    from app.modules.auth.oauth.deployment import issuer_url
    issuer = issuer_url().rstrip("/")
    return {
        "resource": issuer + "/mcp",
        "authorization_servers": [issuer],
        "bearer_methods_supported": ["header"],
    }
