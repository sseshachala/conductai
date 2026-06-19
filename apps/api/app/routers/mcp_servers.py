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
    transport: str = "sse"  # sse | http | stdio
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
    existing = db.execute(text("SELECT is_system FROM mcp_servers WHERE id = :id AND workspace_id = :ws"),
                          {"id": server_id, "ws": workspace_id}).fetchone()
    is_system = existing and existing.is_system
    # System entries: only transport can change
    if is_system:
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
