"""
Projects — logical grouping of resources within a workspace/team.
Routes: /workspaces/{workspace_id}/projects
"""
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_workspace_role, audit as _audit
from app.core.database import get_db

router = APIRouter(prefix="/workspaces/{workspace_id}/projects", tags=["workspace-projects"])


class ProjectOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    created_at: datetime
    agent_count: int = 0


class ProjectCreate(BaseModel):
    name: str


def _enforce_workspace(path_id: str, active_id: str) -> None:
    if path_id != active_id:
        raise HTTPException(status_code=403, detail="Project not found")


@router.get("", response_model=list[ProjectOut])
def list_projects(
    workspace_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    active_workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
    db: Session = Depends(get_db),
):
    _enforce_workspace(workspace_id, active_workspace_id)
    rows = db.execute(text("""
        SELECT p.id, p.workspace_id, p.name, p.created_at,
               COUNT(w.id) AS agent_count
        FROM projects p
        LEFT JOIN workflows w ON w.project_id = p.id
        WHERE p.workspace_id = :ws
        GROUP BY p.id
        ORDER BY p.created_at ASC
    """), {"ws": workspace_id}).fetchall()
    return [ProjectOut(id=str(r.id), workspace_id=str(r.workspace_id), name=r.name,
                       created_at=r.created_at, agent_count=r.agent_count or 0)
            for r in rows]


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    workspace_id: str,
    body: ProjectCreate,
    user_id: Annotated[str, Depends(get_user_id)],
    active_workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor")),
    db: Session = Depends(get_db),
):
    _enforce_workspace(workspace_id, active_workspace_id)
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Project name cannot be empty")

    project_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    db.execute(text("""
        INSERT INTO projects (id, workspace_id, name, created_at)
        VALUES (:id, :ws, :name, :now)
    """), {"id": str(project_id), "ws": workspace_id, "name": body.name.strip(), "now": now})
    db.commit()
    return ProjectOut(id=str(project_id), workspace_id=workspace_id,
                      name=body.name.strip(), created_at=now)


@router.patch("/{project_id}", response_model=ProjectOut)
def rename_project(
    workspace_id: str,
    project_id: str,
    body: dict,
    active_workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
):
    _enforce_workspace(workspace_id, active_workspace_id)
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be empty")
    result = db.execute(text("""
        UPDATE projects SET name = :name
        WHERE id = :id AND workspace_id = :ws
        RETURNING id
    """), {"name": name, "id": project_id, "ws": workspace_id})
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Project not found")
    db.commit()

    row = db.execute(text("""
        SELECT p.id, p.workspace_id, p.name, p.created_at, COUNT(w.id) AS agent_count
        FROM projects p LEFT JOIN workflows w ON w.project_id = p.id
        WHERE p.id = :id GROUP BY p.id
    """), {"id": project_id}).fetchone()
    return ProjectOut(id=str(row.id), workspace_id=str(row.workspace_id), name=row.name,
                      created_at=row.created_at, agent_count=row.agent_count or 0)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    workspace_id: str,
    project_id: str,
    active_workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
):
    _enforce_workspace(workspace_id, active_workspace_id)
    row = db.execute(text(
        "SELECT id FROM projects WHERE id = :id AND workspace_id = :ws"
    ), {"id": project_id, "ws": workspace_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    # Null out project_id on workflows (don't delete the agents)
    db.execute(text("UPDATE workflows SET project_id = NULL WHERE project_id = :pid"),
               {"pid": project_id})
    db.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})
    db.commit()


# ── Audit log endpoint ────────────────────────────────────────────────────────

audit_router = APIRouter(prefix="/workspaces/{workspace_id}/audit-log", tags=["audit-log"])


@audit_router.get("")
def list_audit_log(
    workspace_id: str,
    active_workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
    db: Session = Depends(get_db),
    action: str | None = None,
    actor_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    """Return paginated audit log entries. Admin-only."""
    _enforce_workspace(workspace_id, active_workspace_id)
    q = "SELECT id, actor_id, actor_email, actor_role, action, resource_type, resource_id, metadata, created_at FROM audit_log WHERE workspace_id = :ws"
    params: dict = {"ws": workspace_id}
    if action:
        q += " AND action = :action"
        params["action"] = action
    if actor_id:
        q += " AND actor_id = :actor_id"
        params["actor_id"] = actor_id
    q += " ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
    params["limit"] = min(limit, 200)
    params["offset"] = offset
    rows = db.execute(text(q), params).fetchall()
    return [
        {
            "id": str(r.id),
            "actor_id": r.actor_id,
            "actor_email": r.actor_email,
            "actor_role": r.actor_role,
            "action": r.action,
            "resource_type": r.resource_type,
            "resource_id": r.resource_id,
            "metadata": r.meta,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
