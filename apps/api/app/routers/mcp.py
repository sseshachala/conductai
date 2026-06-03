"""
POST /mcp/tools  — discover tools from an MCP server via credential handle
"""
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id
from app.core.database import get_db

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/mcp", tags=["mcp"])


class ToolDiscoveryRequest(BaseModel):
    credential_key: str
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
    from app.core.crypto import decrypt
    from app.models.integration import Integration

    row = db.query(Integration).filter(
        Integration.workspace_id == workspace_id,
        Integration.handle == body.credential_key,
    ).first()
    if not row or not row.encrypted_credentials:
        raise HTTPException(status_code=404, detail=f"MCP credential '{body.credential_key}' not found")

    creds = decrypt(row.encrypted_credentials)
    server_url = creds.get("server_url") or creds.get("url")
    token = creds.get("token") or creds.get("api_key")
    if not server_url:
        raise HTTPException(status_code=422, detail="Credential missing 'server_url'")

    try:
        from app.runtime.integrations.mcp_client import list_tools
        tools, transport_used = list_tools(server_url, token=token, transport=body.transport)
    except Exception as e:
        log.warning("mcp.discover_failed", credential_key=body.credential_key, error=str(e))
        raise HTTPException(status_code=502, detail=f"MCP connection failed: {e}")

    return ToolDiscoveryResponse(
        tools=[ToolDef(**t) for t in tools],
        transport_used=transport_used,
    )
