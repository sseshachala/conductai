"""
GET    /mcp-servers                 — list MCP servers for workspace (filter by environment_id optional)
POST   /mcp-servers                 — create MCP server
PATCH  /mcp-servers/{id}            — update MCP server
DELETE /mcp-servers/{id}            — delete MCP server
"""
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_permission
from app.core.crypto import decrypt, encrypt
from app.core.database import get_db
from app.runtime.mcp_governance import (
    MCPGovernanceDenied,
    assert_connectable,
    fingerprint,
    transition,
)

router = APIRouter(prefix="/mcp-servers", tags=["mcp-servers"])


class McpServerIn(BaseModel):
    name: str
    url: str
    transport: str = "auto"  # auto | sse | http | stdio
    auth_token: Optional[str] = None
    environment_id: Optional[str] = None


class McpServerOut(BaseModel):
    id: str
    workspace_id: str
    environment_id: Optional[str]
    name: str
    url: str
    transport: str
    has_auth: bool
    is_system: bool
    created_at: datetime
    governance: dict | None = None


def _row_to_out(r) -> McpServerOut:
    return McpServerOut(
        id=str(r.id),
        workspace_id=str(r.workspace_id),
        environment_id=str(r.environment_id) if r.environment_id else None,
        name=r.name,
        url=r.url,
        transport=r.transport,
        has_auth=bool(r.encrypted_auth),
        is_system=bool(r.is_system),
        created_at=r.created_at,
        governance=getattr(r, "governance", None),
    )


@router.get("", response_model=list[McpServerOut])
def list_mcp_servers(
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _: Annotated[str, Depends(require_permission("platform.workflows.view"))],
    db: Session = Depends(get_db),
    environment_id: Optional[str] = None,
):
    query = "SELECT * FROM mcp_servers WHERE workspace_id = :ws"
    params: dict = {"ws": workspace_id}
    if environment_id:
        query += " AND (environment_id = :env OR environment_id IS NULL)"
        params["env"] = environment_id
    query += " ORDER BY name"
    rows = db.execute(text(query), params).fetchall()
    return [_row_to_out(r) for r in rows]


@router.post("", response_model=McpServerOut, status_code=201)
def create_mcp_server(
    body: McpServerIn,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _: Annotated[str, Depends(require_permission("platform.workspace.edit"))],
    db: Session = Depends(get_db),
):
    encrypted = encrypt({"token": body.auth_token}) if body.auth_token else None
    row = db.execute(text("""
        INSERT INTO mcp_servers (id, workspace_id, environment_id, name, url, transport, encrypted_auth, created_at)
        VALUES (gen_random_uuid(), :ws, :env, :name, :url, :transport, :auth, :now)
        RETURNING *
    """), {
        "ws": workspace_id,
        "env": body.environment_id,
        "name": body.name,
        "url": body.url,
        "transport": body.transport,
        "auth": encrypted,
        "now": datetime.now(timezone.utc),
    }).fetchone()
    db.commit()
    return _row_to_out(row)


@router.patch("/{server_id}", response_model=McpServerOut)
def update_mcp_server(
    server_id: str,
    body: McpServerIn,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _: Annotated[str, Depends(require_permission("platform.workspace.edit"))],
    db: Session = Depends(get_db),
):
    encrypted = encrypt({"token": body.auth_token}) if body.auth_token else None
    existing = db.execute(text("SELECT is_system, name FROM mcp_servers WHERE id = :id AND workspace_id = :ws FOR UPDATE"),
                          {"id": server_id, "ws": workspace_id}).fetchone()
    is_system = existing and existing.is_system
    is_conduct_managed = existing and existing.name == "Conduct AI Guard"
    # Conduct AI Guard: token managed by us, only transport can change
    # Public system servers (GitHub, Slack, Linear): user provides their own token
    if is_conduct_managed:
        row = db.execute(text("""
            UPDATE mcp_servers SET transport = :transport
            WHERE id = :id AND workspace_id = :ws RETURNING *
        """), {"transport": body.transport, "id": server_id, "ws": workspace_id}).fetchone()
    else:
        row = db.execute(text("""
            UPDATE mcp_servers
            SET name = :name, url = :url, transport = :transport,
                environment_id = :env,
                encrypted_auth = COALESCE(:auth, encrypted_auth)
            WHERE id = :id AND workspace_id = :ws
            RETURNING *
        """), {
            "id": server_id, "ws": workspace_id,
            "env": body.environment_id,
            "name": body.name, "url": body.url, "transport": body.transport,
            "auth": encrypted,
        }).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if getattr(row, "governance", None):
        import json
        current = row.governance
        state = current["state"] if current["state"] in {"quarantined", "revoked"} else "needs_review"
        row = db.execute(text("UPDATE mcp_servers SET governance = CAST(:value AS jsonb) "
                              "WHERE id = :id AND workspace_id = :ws RETURNING *"),
                         {"id": server_id, "ws": workspace_id,
                          "value": json.dumps({"state": state, "revision": current["revision"] + 1})}).fetchone()
    db.commit()
    return _row_to_out(row)


class McpTestIn(BaseModel):
    url: str
    auth_token: Optional[str] = None
    transport: str = "auto"
    environment_id: Optional[str] = None
    credential_key: Optional[str] = None  # e.g. GITHUB_TOKEN — resolve from env if auth_token blank
    server_id: Optional[str] = None  # when set, fall back to this server's saved token if auth_token blank


class McpTestOut(BaseModel):
    ok: bool
    tool_count: int = 0
    sample_tools: list[str] = []
    transport_used: str = ""
    error: Optional[str] = None


@router.post("/test-connection", response_model=McpTestOut)
def test_mcp_connection(
    body: McpTestIn,
    _: str = Depends(require_permission("platform.credentials.manage")),
    workspace_id: Annotated[str, Depends(get_workspace_id)] = "",
    db: Session = Depends(get_db),
):
    """Call tools/list on the candidate MCP server with the user-supplied auth.

    Returns ok=True with a tool sample on success, ok=False with the underlying
    error message on failure. Saves the user a 30-minute agent run that fails
    at the first tool call because the token was wrong.

    Auth resolution chain (first hit wins):
      1. ``body.auth_token`` — the token typed into the form. Lets the user
         validate a NEW token before overwriting the saved one.
      2. ``body.server_id`` — decrypts the saved token for that row (workspace-
         scoped). Lets the user re-test an existing config without re-typing.
      3. ``body.credential_key`` — resolves via workspace env-var table.
    """
    from app.runtime.integrations.mcp_client import list_tools

    token = body.auth_token or None
    if body.server_id:
        # Workspace-scoped lookup — never leak another workspace's token.
        row = db.execute(
            text(
                "SELECT encrypted_auth, url, governance FROM mcp_servers "
                "WHERE id = :id AND workspace_id = :ws"
            ),
            {"id": body.server_id, "ws": workspace_id},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="MCP server not found")
        if body.url != row.url:
            raise HTTPException(status_code=422, detail="Saved credentials require the registered server URL")
        try:
            assert_connectable(row.governance)
        except MCPGovernanceDenied as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        if not token and row.encrypted_auth:
            try:
                token = decrypt(row.encrypted_auth).get("token")
            except Exception:
                token = None
    if not token and body.credential_key:
        try:
            from app.runtime.mcp_credentials import resolve_mcp_token_by_credential_key
            token = resolve_mcp_token_by_credential_key(
                body.credential_key, workspace_id, body.environment_id or None, db
            )
        except Exception:
            pass

    try:
        tools, transport_used = list_tools(body.url, token, body.transport)
    except Exception as e:
        # ponytail: str(e) is empty for CancelledError, bare Exception(), or
        # anyio ExceptionGroup with a naked inner — the UI then shows
        # "Connection failed" with no cause. Always include the type name
        # + a hint about whether we even had a token so the failure is
        # actionable instead of opaque.
        msg = str(e).strip() or repr(e) or type(e).__name__
        token_hint = "" if token else " (no token was available — check auth_token / server_id / credential_key)"
        return McpTestOut(ok=False, error=f"{type(e).__name__}: {msg}{token_hint}"[:300])

    sample = [t.get("name", "") for t in tools[:5] if t.get("name")]
    return McpTestOut(
        ok=True,
        tool_count=len(tools),
        sample_tools=sample,
        transport_used=transport_used,
    )


class McpToolOut(BaseModel):
    name: str
    description: str
    inputSchema: dict
    outputSchema: dict | None = None
    annotations: dict | None = None
    title: str | None = None


_MCP_TOOLS_CACHE_TTL = 300  # 5 minutes


def _redis_client():
    import redis as _redis

    from app.core.config import settings as _settings
    return _redis.from_url(_settings.redis_url, decode_responses=True)


@router.get("/{server_id}/tools", response_model=list[McpToolOut])
def list_mcp_server_tools(
    server_id: str,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _: Annotated[str, Depends(require_permission("platform.workflows.view"))],
    db: Session = Depends(get_db),
    response: Response = None,
):
    """List tools exposed by an MCP server. Results are cached for 5 minutes."""
    from app.runtime.integrations.mcp_client import list_tools

    row = db.execute(
        text("SELECT * FROM mcp_servers WHERE id = :id AND workspace_id = :ws"),
        {"id": server_id, "ws": workspace_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="MCP server not found")

    try:
        assert_connectable(row.governance)
    except MCPGovernanceDenied as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    cache_key = f"mcp_tools:{server_id}"
    try:
        r = _redis_client()
        cached = r.get(cache_key)
        if cached and not row.governance:
            import json as _json
            return _json.loads(cached)
    except Exception:
        pass

    token = decrypt(row.encrypted_auth).get("token") if row.encrypted_auth else None
    try:
        tools, _ = list_tools(row.url, token, row.transport or "auto")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MCP server unreachable: {exc!s:.200}")

    if row.governance:
        import json
        try:
            digest = fingerprint(tools)
        except MCPGovernanceDenied as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        observed = {**row.governance, "observed_digest": digest,
                    "observed_at": datetime.now(timezone.utc).isoformat(), "tool_count": len(tools)}
        # Do not overwrite concurrent quarantine, edits, or approvals during network I/O.
        result = db.execute(text("UPDATE mcp_servers SET governance = CAST(:value AS jsonb) "
                        "WHERE id = :id AND workspace_id = :ws AND governance = CAST(:previous AS jsonb)"),
                   {"id": server_id, "ws": workspace_id, "value": json.dumps(observed),
                    "previous": json.dumps(row.governance)})
        if result.rowcount != 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="MCP review changed; reload before retrying")
        db.commit()
        if response is not None:
            response.headers["X-Conduct-MCP-Digest"] = digest

    try:
        import json as _json
        r = _redis_client()
        r.setex(cache_key, _MCP_TOOLS_CACHE_TTL, _json.dumps(tools))
    except Exception:
        pass

    return tools


class McpReviewIn(BaseModel):
    action: Literal["require_review", "approve", "quarantine", "revoke", "restore"]
    revision: int = Field(ge=0, strict=True)
    digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


@router.post("/{server_id}/inspect")
def inspect_mcp_server(
    server_id: uuid.UUID,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _: Annotated[str, Depends(require_permission("platform.credentials.manage"))],
    db: Session = Depends(get_db),
):
    response = Response()
    tools = list_mcp_server_tools(str(server_id), workspace_id, _, db, response)
    return {"tools": tools, "digest": response.headers.get("X-Conduct-MCP-Digest")}


@router.post("/{server_id}/review", response_model=McpServerOut)
def review_mcp_server(
    server_id: uuid.UUID,
    body: McpReviewIn,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    actor: Annotated[str, Depends(get_user_id)],
    _: Annotated[str, Depends(require_permission("platform.workspace.edit"))],
    db: Session = Depends(get_db),
):
    import json

    from app.models.audit_log import AuditLog

    row = db.execute(text("SELECT * FROM mcp_servers WHERE id = :id AND workspace_id = :ws FOR UPDATE"),
                     {"id": str(server_id), "ws": workspace_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="MCP server not found")
    if (row.governance or {}).get("revision", 0) != body.revision:
        raise HTTPException(status_code=409, detail="MCP review changed; reload before retrying")
    try:
        updated = transition(row.governance, body.action, body.digest)
    except MCPGovernanceDenied as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    updated["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = db.execute(text("UPDATE mcp_servers SET governance = CAST(:value AS jsonb), "
                             "encrypted_auth = CASE WHEN :revoke THEN NULL ELSE encrypted_auth END "
                             "WHERE id = :id AND workspace_id = :ws RETURNING *"),
                        {"id": str(server_id), "ws": workspace_id, "value": json.dumps(updated),
                         "revoke": body.action == "revoke"}).fetchone()
    db.add(AuditLog(workspace_id=uuid.UUID(workspace_id), actor_id=actor,
                    action="mcp." + body.action, resource_type="mcp_server", resource_id=str(server_id),
                    meta={"state": updated["state"], "revision": updated["revision"],
                          "digest": updated.get("approved_digest")}))
    db.commit()
    return _row_to_out(result)


@router.delete("/{server_id}", status_code=204)
def delete_mcp_server(
    server_id: str,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _: Annotated[str, Depends(require_permission("platform.workspace.edit"))],
    db: Session = Depends(get_db),
):
    existing = db.execute(text("SELECT is_system FROM mcp_servers WHERE id = :id AND workspace_id = :ws"),
                          {"id": server_id, "ws": workspace_id}).fetchone()
    if existing and existing.is_system:
        raise HTTPException(status_code=403, detail="System MCP servers cannot be deleted")
    result = db.execute(text(
        "DELETE FROM mcp_servers WHERE id = :id AND workspace_id = :ws"
    ), {"id": server_id, "ws": workspace_id})
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="MCP server not found")
