"""
ConductGuard — Remote MCP server over HTTP.

POST /guard/mcp   — stateless JSON-RPC 2.0 endpoint (MCP HTTP transport)

Claude.ai / Claude for Work users add this URL in their MCP settings:
  https://api.conductai.ai/guard/mcp?workspace_id=<uuid>
  Authorization: Bearer <member_token>

Claude Desktop users can also point here instead of running a local process.
Auth: workspace_id in query, member_token in `Authorization: Bearer` header.
Legacy `?token=` query param accepted for Claude.ai web compat — emits a
deprecation warning (issue #800). Slated for removal in issue #810.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from sqlalchemy import text as _sql

from app.core.database import SessionLocal
from app.core.auth import get_clerk_user_email, resolve_agent_token
from app.modules.guard.models import GuardConfig  # noqa: F401 — kept: tests patch routers.mcp.GuardConfig
from app.modules.guard.routers.mcp_tool_catalog import (  # noqa: F401 — re-exports
    PROTOCOL_VERSION, _TOOLS,
)
from app.modules.guard.routers.mcp_helpers import (  # noqa: F401 — re-exports
    _ACTION_PRIORITY, _APPROVAL_FIELDS, _PERSONAS, _detect_surface, _err, _get_rules,
    _get_run_status, _list_agents, _list_playbooks, _list_projects, _match_policy, _ok,
    _project_rule, _record_event, _run_workflow, _text, _tool_ws_ctx,
)

router = APIRouter(prefix="/guard/mcp", tags=["guard-mcp"])


# ── Main endpoint ─────────────────────────────────────────────────────────────

def _extract_token(request: Request) -> str | None:
    """Authorization header only. Header may be `Bearer <token>` or a bare token
    (Smithery-style). ?token= query param was retired with issue #800."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:].strip() or None
    if auth:
        return auth.strip() or None
    return None


@router.get("")
async def mcp_sse(
    request: Request,
    workspace_id: str | None = Query(None),
):
    """SSE endpoint required by MCP Streamable HTTP transport (GET establishes the stream).
    For stateless policy checks we don't push server-initiated messages, so this just
    holds the connection open with keepalive pings until the client disconnects.

    Auth: Authorization: Bearer <token> header required.
    workspace_id is optional — when omitted, the Bearer token identifies the workspace.
    """
    import asyncio

    if not _extract_token(request):
        ua = request.headers.get("User-Agent", "")
        # Only send OAuth discovery header to clients that support it.
        # Smithery and similar tools fall back to API key auth — sending WWW-Authenticate
        # breaks them. Claude.ai sends "claude-mcp"; VS Code Copilot sends "github-copilot".
        _ua = ua.lower()
        is_claude = "claude" in _ua or "github-copilot" in _ua or "vscode" in _ua or "cursor" in _ua
        resp_headers = {}
        if is_claude:
            ws_param = f"?workspace_id={workspace_id}" if workspace_id else ""
            resp_headers["WWW-Authenticate"] = (
                'Bearer realm="https://api.conductai.ai/guard/mcp",'
                f' resource_metadata="https://api.conductai.ai/.well-known/oauth-protected-resource/guard/mcp{ws_param}"'
            )
        return JSONResponse(
            status_code=401,
            content={"error": "missing or invalid token"},
            headers=resp_headers,
        )

    # Build the POST endpoint URL from the request so it works across envs.
    # Behind Render's TLS proxy request.base_url is http:// unless uvicorn is
    # started with --proxy-headers; trust X-Forwarded-Proto as fallback so the
    # SSE endpoint origin matches the connection origin (MCP requires match).
    fwd_proto = request.headers.get("x-forwarded-proto", "").split(",")[0].strip()
    base_url = str(request.base_url).rstrip("/")
    if fwd_proto in ("http", "https") and "://" in base_url:
        base_url = f"{fwd_proto}://{base_url.split('://', 1)[1]}"
    post_url = f"{base_url}/guard/mcp"

    async def event_stream():
        # MCP SSE transport: client waits for this before sending initialize
        yield f"event: endpoint\ndata: {post_url}\n\n"
        yield ": keepalive\n\n"
        while True:
            await asyncio.sleep(15)
            yield ": keepalive\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete("")
async def mcp_terminate():
    """Streamable HTTP session termination — stateless server, just ack."""
    return JSONResponse(status_code=204, content=None)


@router.post("")
async def mcp_endpoint(
    request: Request,
    workspace_id: str | None = Query(None, description="Guard workspace UUID — optional when using OAuth Bearer token"),
):
    """Stateless MCP JSON-RPC endpoint for Claude.ai / Claude Desktop / Claude for Work."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(status_code=400, content={"error": "invalid JSON"})

    msg_id = body.get("id")
    method = body.get("method", "")
    params = body.get("params") or {}

    resolved_token = _extract_token(request)
    if not resolved_token:
        return JSONResponse(status_code=401, content=_err(msg_id, -32600, "missing token (use Authorization: Bearer)"))

    db = SessionLocal()
    try:
        ident = resolve_agent_token(resolved_token, db)
        if not ident:
            return JSONResponse(status_code=401, content=_err(msg_id, -32600, "invalid token"))
        _ws_id_str, clerk_user_id = ident

        # Validate workspace matches URL param if provided
        if workspace_id:
            try:
                ws_uuid = uuid.UUID(workspace_id)
            except ValueError:
                return JSONResponse(status_code=422, content=_err(msg_id, -32600, "invalid workspace_id"))
            if str(ws_uuid) != _ws_id_str:
                return JSONResponse(status_code=401, content=_err(msg_id, -32600, "token does not belong to this workspace"))
        else:
            ws_uuid = uuid.UUID(_ws_id_str)

        from starlette.concurrency import run_in_threadpool
        from app.modules.auth.federation.mcp_ingress import prepare
        identity = await run_in_threadpool(prepare, request, str(ws_uuid), resolved_token, body)
        if isinstance(identity, JSONResponse):
            return identity

        user_email = get_clerk_user_email(clerk_user_id) or clerk_user_id

        # ponytail: auto-provision GuardConfig on first MCP call — token already
        # authenticated, workspace exists, missing config was a 401 loop for
        # Claude.ai OAuth (89cc839 re-OAuth trick never converges).
        from app.modules.guard.routers.config import _get_or_create_config
        config = _get_or_create_config(db, str(ws_uuid))

        if method == "initialize":
            client_info = params.get("clientInfo") or {}
            surface = _detect_surface(client_info)
            # Echo the client's requested protocolVersion so strict clients (Copilot
            # rmcp) don't treat the connection as a version mismatch and skip
            # tools/list. Fall back to our default when the client omits it.
            negotiated_version = params.get("protocolVersion") or PROTOCOL_VERSION
            # Streamable HTTP: clients (Copilot rmcp, etc) expect Mcp-Session-Id.
            # We're stateless, so any stable-per-response uuid satisfies the contract.
            session_hdr = str(uuid.uuid4())
            return JSONResponse(
                _ok(msg_id, {
                    "protocolVersion": negotiated_version,
                    "capabilities":    {"tools": {}},
                    "serverInfo":      {"name": "conductguard", "version": "1.0.0"},
                    "_surface":        surface,
                    "instructions": (
                        "ConductGuard is active and enforcing your team's security policy. "
                        # #997: once per intent, not per action — protects the transcript.
                        "Call guard_activity ONCE at the start of a user request with a one-line summary. "
                        "Call guard_check ONCE per intent (not per file/command). Re-check only when scope changes "
                        "— e.g. moving from reads to writes, from local files to network, or entering a new task. "
                        "If the response is BLOCKED: stop and explain the policy rule to the user. "
                        "If WARNING: proceed but surface the warning inline. "
                        "If the response is empty or 'ok': proceed silently — do not narrate it in the chat. "
                        "Do not repeat guard_check for the same intent within a single response."
                    ),
                }),
                headers={"Mcp-Session-Id": session_hdr},
            )

        elif method == "notifications/initialized":
            # Response() not JSONResponse(content=None): the latter serializes
            # `null` (4 bytes) with Content-Length: 0, uvicorn raises
            # RuntimeError("Response content longer than Content-Length"),
            # Claude.ai's toolbox proxy sees a broken response and returns 502.
            return Response(status_code=204)

        elif method == "tools/list":
            return JSONResponse(_ok(msg_id, {"tools": _TOOLS}))

        elif method == "tools/call":
            # ponytail: stamps every tool response with [ws:xxxxxxxx] so the
            # model can detect silent workspace changes without polling.
            _tool_ws_ctx.set(ws_uuid)
            tool_name = params.get("name", "")
            arguments = params.get("arguments") or {}
            # Try explicit surface header, then clientInfo (rarely on tools/call),
            # then User-Agent (Copilot rmcp reveals itself here). Default to
            # 'unknown' — misattributing to claude_chat hides Copilot traffic.
            ai_tool = (
                request.headers.get("x-claude-surface")
                or _detect_surface(params.get("clientInfo") or {})
                or "unknown"
            )
            if ai_tool == "unknown":
                ua_surface = _detect_surface({"name": request.headers.get("User-Agent", "")})
                if ua_surface != "unknown":
                    ai_tool = ua_surface
            session_id = request.headers.get("x-session-id", str(uuid.uuid4()))

            # Legacy MCP sightings do not establish hook or Gateway protection.
            try:
                _now = datetime.now(timezone.utc)
                with db.begin_nested():
                    db.execute(_sql("""
                    INSERT INTO discovered_agents
                        (id, workspace_id, name, framework, source, location, under_guard, proxy_routed, first_seen_at, last_seen_at)
                    VALUES
                        (gen_random_uuid(), :ws, :name, :fw, 'mcp', NULL, false, false, :now, :now)
                    ON CONFLICT (workspace_id, framework, source)
                    DO UPDATE SET under_guard = false, last_seen_at = :now
                """), {"ws": ws_uuid, "name": ai_tool, "fw": ai_tool, "now": _now})
                db.commit()
            except Exception:
                pass  # never block a tool call over a telemetry write


            # #1219 Phase 3b — dispatch is extracted into mcp_impls.py so the
            # /mcp adapter (Phase 3b Chunk B2) can call the same code path.
            # Byte-parity across the two endpoints is guaranteed by construction.
            from app.modules.guard.mcp_impls import GuardCtx, dispatch_guard_tool
            # Look up caller identity's risk_tier for tier-gated policies.
            # Best-effort: guard-mt-* member tokens have no AgentIdentity row,
            # legacy identities may have null tier. Matcher treats null as
            # "no match" for any tier-requiring rule.
            try:
                from app.core.auth import resolve_agent_identity_row
                _ai = resolve_agent_identity_row(resolved_token, db)
                _agent_risk_tier = getattr(_ai, "risk_tier", None) if _ai else None
            except Exception:
                _agent_risk_tier = None
            _gctx = GuardCtx(
                db=db, ws_uuid=ws_uuid, workspace_id=workspace_id,
                resolved_token=resolved_token, clerk_user_id=clerk_user_id,
                user_email=user_email, ai_tool=ai_tool, session_id=session_id,
                agent_risk_tier=_agent_risk_tier,
                identity=identity,
            )
            if identity is not None:
                from app.modules.auth.federation.resolver import FederationDenied, recheck
                from app.modules.auth.federation.mcp_ingress import failure
                from sqlalchemy.exc import SQLAlchemyError
                try:
                    recheck(db, identity, "mcp." + tool_name)
                except FederationDenied as error:
                    return failure(error, msg_id)
                except SQLAlchemyError:
                    return failure(FederationDenied("federation_storage_unavailable", 503), msg_id)
                db.info["federation_identity"] = identity
            return JSONResponse(_text(msg_id, dispatch_guard_tool(tool_name, arguments, _gctx)))

        elif method == "ping":
            return JSONResponse(_ok(msg_id, {}))

        else:
            if msg_id is not None:
                return JSONResponse(_err(msg_id, -32601, f"Method not found: {method}"))
            return JSONResponse(status_code=204, content=None)

    finally:
        db.close()


# ---------------------------------------------------------------------------
# OAuth support endpoints
# ---------------------------------------------------------------------------

well_known_router = APIRouter(tags=["guard-mcp"])


@well_known_router.get("/.well-known/oauth-protected-resource/guard/mcp")
async def oauth_protected_resource(workspace_id: str | None = Query(None)):
    """RFC 9728 — tells OAuth clients where the authorization server lives.

    workspace_id is echoed into the resource URI so it flows into the RFC 8707
    resource parameter that MCP clients (Claude.ai) send to the authorize endpoint.
    """
    resource = "https://api.conductai.ai/guard/mcp"
    if workspace_id:
        resource += f"?workspace_id={workspace_id}"
    return JSONResponse({
        "resource": resource,
        "authorization_servers": [os.environ.get("APP_URL", "https://app.conductai.ai")],
        "bearer_methods_supported": ["header"],
        "scopes_supported": ["guard:read"],
    })


@router.post("/oauth/member-token")
async def oauth_member_token(request: Request):
    """Exchange a Clerk JWT for a long-lived cond_api_* token (Claude.ai OAuth flow).

    Mints or rotates a cond_api_* identity token with created_by_clerk_user_id
    so every MCP call is attributed to the correct user email via GMC join.
    """
    import secrets as _secrets
    from app.core.auth import _verify_clerk_token
    from app.core.crypto import encrypt as _encrypt
    from app.modules.agent_identity.models import AgentIdentity

    _API_PFX = "cond_api_"
    _API_PFX_LEN = len(_API_PFX) + 4

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"error": "missing Clerk token"})

    clerk_token = auth_header[7:].strip()
    claims = _verify_clerk_token(clerk_token)
    if not claims:
        return JSONResponse(status_code=401, content={"error": "invalid Clerk token"})

    body = await request.json()
    workspace_id = body.get("workspace_id", "")
    email = body.get("email", "")

    if not email:
        return JSONResponse(status_code=422, content={"error": "email required"})

    clerk_user_id = claims.get("sub", email)

    db = SessionLocal()
    try:
        if not workspace_id:
            row = db.execute(
                _sql("""
                    SELECT gmc.workspace_id FROM guard_member_config gmc
                    JOIN guard_config gc ON gc.workspace_id = gmc.workspace_id
                    WHERE gmc.clerk_user_id = :uid AND gmc.active = true
                    ORDER BY gmc.joined_at DESC LIMIT 1
                """),
                {"uid": clerk_user_id},
            ).fetchone()
            if not row:
                return JSONResponse(status_code=404, content={"error": "no guard workspace found for this user — join via invite first"})
            workspace_id = str(row.workspace_id)

        try:
            ws_uuid = uuid.UUID(workspace_id)
        except ValueError:
            return JSONResponse(status_code=422, content={"error": "invalid workspace_id"})

        plaintext = _API_PFX + _secrets.token_urlsafe(32)
        prefix = plaintext[:_API_PFX_LEN]
        now = datetime.now(timezone.utc)

        # Reuse existing OAuth identity for this user if present, rotate token
        existing = db.execute(
            _sql("""
                SELECT ai.id FROM agent_identities ai
                JOIN guard_member_config gmc ON gmc.agent_identity_id = ai.id
                WHERE gmc.workspace_id = :ws AND gmc.clerk_user_id = :uid
                  AND ai.token_type = 'api'
                LIMIT 1
            """),
            {"ws": str(ws_uuid), "uid": clerk_user_id},
        ).fetchone()

        if existing:
            identity = db.query(AgentIdentity).filter(AgentIdentity.id == existing.id).first()
            identity.token_prefix = prefix
            identity.token_encrypted = _encrypt({"token": plaintext})
            identity.last_used_at = now
        else:
            identity = AgentIdentity(
                id=str(uuid.uuid4()),
                workspace_id=ws_uuid,
                name=f"Claude.ai ({email})",
                provider="conduct",
                token_prefix=prefix,
                token_encrypted=_encrypt({"token": plaintext}),
                token_type="api",
                token_name="claude-ai-oauth",
                created_by_clerk_user_id=clerk_user_id,
                created_at=now,
                last_used_at=now,
                expires_at=None,  # long-lived — no expiry
            )
            db.add(identity)
            # ponytail: no UPDATE guard_member_config here — GMC.agent_identity_id
            # must stay pointing at the CLI cond_agt_* token. OAuth tokens resolve
            # via created_by_clerk_user_id fallback in resolve_agent_token instead.

        db.commit()
        return JSONResponse({"member_token": plaintext})
    finally:
        db.close()
