"""
GET    /mcp-servers                 — list MCP servers for workspace (filter by environment_id optional)
POST   /mcp-servers                 — create MCP server
PATCH  /mcp-servers/{id}            — update MCP server
DELETE /mcp-servers/{id}            — delete MCP server
"""
import uuid
from typing import Annotated, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_permission
from app.core.crypto import encrypt, decrypt
from app.core.database import get_db

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
    existing = db.execute(text("SELECT is_system, name FROM mcp_servers WHERE id = :id AND workspace_id = :ws"),
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
    db.commit()
    return _row_to_out(row)


class McpTestIn(BaseModel):
    url: str
    auth_token: Optional[str] = None
    transport: str = "auto"
    environment_id: Optional[str] = None
    credential_key: Optional[str] = None  # e.g. GITHUB_TOKEN — resolve from env if auth_token blank


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
    """
    from app.runtime.integrations.mcp_client import list_tools

    token = body.auth_token or None
    # If no inline token but environment + credential_key provided, resolve from Integration store
    if not token and body.environment_id and body.credential_key:
        try:
            from app.routers.credentials import _ENV_VAR_MAP
            from app.models.integration import Integration
            from app.core.crypto import decrypt as _dec
            handle, field = _ENV_VAR_MAP.get(body.credential_key, (None, None))
            if handle:
                row = db.query(Integration).filter(
                    Integration.workspace_id == workspace_id,
                    Integration.environment_id == body.environment_id,
                    Integration.handle == handle,
                ).first()
                if row and row.encrypted_credentials:
                    creds = _dec(row.encrypted_credentials) or {}
                    token = creds.get(field) or None
        except Exception:
            pass

    try:
        tools, transport_used = list_tools(body.url, token, body.transport)
    except Exception as e:
        return McpTestOut(ok=False, error=str(e)[:300])

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
):
    """List tools exposed by an MCP server. Results are cached for 5 minutes."""
    from app.runtime.integrations.mcp_client import list_tools

    row = db.execute(
        text("SELECT * FROM mcp_servers WHERE id = :id AND workspace_id = :ws"),
        {"id": server_id, "ws": workspace_id},
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="MCP server not found")

    cache_key = f"mcp_tools:{server_id}"
    try:
        r = _redis_client()
        cached = r.get(cache_key)
        if cached:
            import json as _json
            return _json.loads(cached)
    except Exception:
        pass

    token = decrypt(row.encrypted_auth).get("token") if row.encrypted_auth else None
    try:
        tools, _ = list_tools(row.url, token, row.transport or "auto")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MCP server unreachable: {exc!s:.200}")

    try:
        import json as _json
        r = _redis_client()
        r.setex(cache_key, _MCP_TOOLS_CACHE_TTL, _json.dumps(tools))
    except Exception:
        pass

    return tools


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
