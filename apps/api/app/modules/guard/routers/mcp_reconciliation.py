"""Workspace-scoped, administrator-owned associations for passive MCP findings."""
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_permission
from app.core.database import get_db
from app.models.audit_log import AuditLog
from app.models.mcp_server import McpServer
from app.modules.guard.discovery_inventory import agent_view, clean_mcp_servers
from app.modules.guard.mcp_reconciliation import reconcile, registration_view
from app.modules.guard.models import DiscoveredAgent

router = APIRouter()


def registrations(db, workspace_id):
    rows = db.query(McpServer.id, McpServer.name, McpServer.governance).filter(
        McpServer.workspace_id == uuid.UUID(workspace_id)).order_by(McpServer.name, McpServer.id).all()
    return {str(row.id): registration_view(row) for row in rows}


@router.get("/mcp-reconciliation")
def list_reconciliation(
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _: Annotated[str, Depends(require_permission("platform.workflows.view"))],
    db: Session = Depends(get_db), limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0),
):
    registered = registrations(db, workspace_id)
    rows = db.query(DiscoveredAgent).filter(
        DiscoveredAgent.workspace_id == uuid.UUID(workspace_id),
        DiscoveredAgent.device_id.isnot(None), DiscoveredAgent.installation_id.isnot(None),
    ).order_by(DiscoveredAgent.last_seen_at.desc(), DiscoveredAgent.id).offset(offset).limit(limit + 1).all()
    now = datetime.now(timezone.utc)
    return {"registrations": list(registered.values()),
            "installations": [reconcile(row, registered, now) for row in rows[:limit]],
            "next_offset": offset + limit if len(rows) > limit else None}


class McpLinkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server_id: uuid.UUID | None
    revision: int = Field(ge=0)


@router.put("/agents/{agent_id}/mcp-links/{reference_id}")
def link_registration(
    agent_id: uuid.UUID,
    reference_id: Annotated[str, Path(pattern=r"^[a-f0-9]{64}$")],
    body: McpLinkIn,
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    actor: Annotated[str, Depends(get_user_id)],
    _: Annotated[str, Depends(require_permission("platform.workspace.edit"))],
    db: Session = Depends(get_db),
):
    row = db.query(DiscoveredAgent).filter(
        DiscoveredAgent.id == agent_id, DiscoveredAgent.workspace_id == uuid.UUID(workspace_id),
    ).with_for_update().populate_existing().first()
    if row is None:
        raise HTTPException(404, "Installation not found")
    current = row.mcp_links or {}
    if current.get("revision", 0) != body.revision:
        raise HTTPException(409, "MCP associations changed; refresh before retrying")
    bindings = dict(current.get("bindings", {}))
    if body.server_id is not None:
        view = agent_view(row)
        if view["freshness"] != "fresh" or view["evidence"].get("config_unreadable"):
            raise HTTPException(409, "Rescan this installation before linking")
        findings = clean_mcp_servers((row.evidence or {}).get("mcp_servers"))
        if reference_id not in {item["id"] for item in findings}:
            raise HTTPException(404, "MCP reference not found in the latest scan")
        server = db.query(McpServer.id).filter(
            McpServer.id == body.server_id, McpServer.workspace_id == uuid.UUID(workspace_id),
        ).first()
        if server is None:
            raise HTTPException(404, "MCP registration not found")
        if reference_id not in bindings and len(bindings) >= 100:
            raise HTTPException(409, "Remove old associations before linking more servers")
        bindings[reference_id] = {"server_id": str(body.server_id), "linked_at": datetime.now(timezone.utc).isoformat()}
    else:
        bindings.pop(reference_id, None)
    row.mcp_links = {"revision": body.revision + 1, "bindings": bindings}
    db.add(AuditLog(workspace_id=uuid.UUID(workspace_id), actor_id=actor,
                    action="mcp.inventory.linked" if body.server_id else "mcp.inventory.unlinked",
                    resource_type="discovered_agent", resource_id=str(agent_id),
                    meta={"reference_id": reference_id, "server_id": str(body.server_id) if body.server_id else None,
                          "revision": row.mcp_links["revision"]}))
    db.commit()
    return reconcile(row, registrations(db, workspace_id))
