"""
POST /mcp/tools  — discover tools from an MCP server via credential handle or server_id
"""
import structlog
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id
from app.core.database import get_db

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/mcp", tags=["mcp"])


class ToolDiscoveryRequest(BaseModel):
    credential_key: Optional[str] = None
    server_id: Optional[str] = None
    transport: str = "auto"


class ToolDef(BaseModel):
    name: str
    description: str
    inputSchema: dict


class ToolDiscoveryResponse(BaseModel):
    tools: list[ToolDef]
    transport_used: str


@router.post("/tools", response_model=ToolDiscoveryResponse)
def discover_mcp_tools(
    body: ToolDiscoveryRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    from app.core.crypto import decrypt as _decrypt

    if body.server_id is not None:
        row = db.execute(
            text(
                "SELECT url, transport, encrypted_auth"
                " FROM mcp_servers"
                " WHERE id = :id AND workspace_id = :ws"
            ),
            {"id": body.server_id, "ws": workspace_id},
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="MCP server not found")
        server_url = row.url
        transport = row.transport or body.transport
        token = _decrypt(row.encrypted_auth).get("token") if row.encrypted_auth else None
    elif body.credential_key is not None:
        from app.core.credentials import get_credential as _get_credential

        creds = _get_credential(db, workspace_id, body.credential_key)
        if not creds:
            raise HTTPException(
                status_code=404,
                detail=f"MCP credential '{body.credential_key}' not found",
            )
        server_url = creds.get("server_url") or creds.get("url")
        token = creds.get("token") or creds.get("api_key")
        transport = body.transport
        if not server_url:
            raise HTTPException(status_code=422, detail="Credential missing 'server_url'")
    else:
        raise HTTPException(
            status_code=422, detail="Either 'server_id' or 'credential_key' is required"
        )

    try:
        from app.runtime.integrations.mcp_client import list_tools
        tools, transport_used = list_tools(server_url, token=token, transport=transport)
    except Exception as e:
        log.warning(
            "mcp.discover_failed",
            server_id=body.server_id,
            credential_key=body.credential_key,
            error=str(e),
        )
        raise HTTPException(status_code=502, detail=f"MCP connection failed: {e}")

    return ToolDiscoveryResponse(
        tools=[ToolDef(**t) for t in tools],
        transport_used=transport_used,
    )
