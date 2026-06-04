"""
Projects — logical grouping of resources within a workspace/team.
Routes: /workspaces/{workspace_id}/projects
"""
import re
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
preferences_router = APIRouter(prefix="/workspaces/{workspace_id}/preferences", tags=["workspace-preferences"])
notifications_router = APIRouter(prefix="/workspaces/{workspace_id}/notifications", tags=["notifications"])


class ProjectOut(BaseModel):
    id: str
    workspace_id: str
    name: str
    slug: str = ""
    created_at: datetime
    agent_count: int = 0


class ProjectCreate(BaseModel):
    name: str


def _to_relative_time(dt: datetime | None) -> str:
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    delta = now - dt
    seconds = int(max(delta.total_seconds(), 0))
    if seconds < 60:
        return "now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    return f"{days}d"


def _notification_tone(action: str) -> str:
    a = (action or "").lower()
    if any(x in a for x in ["failed", "error", "denied", "blocked", "deleted"]):
        return "err"
    if any(x in a for x in ["approval", "warn", "paused"]):
        return "warn"
    return "ok"


@notifications_router.get("")
def list_notifications(
    workspace_id: str,
    active_workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
    db: Session = Depends(get_db),
    limit: int = 10,
):
    """Return recent notification-like events from audit_log for the workspace."""
    _enforce_workspace(workspace_id, active_workspace_id)
    rows = db.execute(
        text(
            """
            SELECT id, action, resource_type, resource_id, metadata AS meta, created_at
            FROM audit_log
            WHERE workspace_id = :ws
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"ws": workspace_id, "limit": min(max(limit, 1), 50)},
    ).fetchall()

    items = []
    for r in rows:
        action = r.action or "activity"
        title = action.replace(".", " ").replace("_", " ").strip().title()
        meta = r.meta if isinstance(r.meta, dict) else {}
        resource = r.resource_id or ""
        desc_parts = []
        if r.resource_type:
            desc_parts.append(str(r.resource_type))
        if resource:
            desc_parts.append(str(resource))
        if not desc_parts and meta:
            # Small, safe summary fallback from metadata keys.
            keys = [k for k in ["workflow_id", "run_id", "credential_id", "project_id"] if k in meta]
            desc_parts.extend([str(meta[k]) for k in keys[:2]])

        items.append(
            {
                "id": str(r.id),
                "title": title,
                "tone": _notification_tone(action),
                "desc": " · ".join(desc_parts) if desc_parts else "Workspace activity",
                "time": _to_relative_time(r.created_at),
                # Until we store read state per user, treat recent items as unread in UI.
                "unread": True,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )

    return {"items": items, "unread_count": len(items)}


def _slugify(name: str) -> str:
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)
    s = re.sub(r"[\s_]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-") or "project"


def _unique_slug(base: str, workspace_id: str, db: Session, exclude_id: str | None = None) -> str:
    n = 0
    while True:
        slug = base if n == 0 else f"{base}-{n}"
        q = "SELECT 1 FROM projects WHERE workspace_id = :ws AND slug = :slug"
        params: dict = {"ws": workspace_id, "slug": slug}
        if exclude_id:
            q += " AND id != :eid"
            params["eid"] = exclude_id
        if not db.execute(text(q), params).fetchone():
            return slug
        n += 1


def _enforce_workspace(path_id: str, active_id: str) -> None:
    if path_id != active_id:
        raise HTTPException(status_code=403, detail="Project not found")


@router.get("", response_model=list[ProjectOut])
def list_projects(
    workspace_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    active_workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
    db: Session = Depends(get_db),
):
    _enforce_workspace(workspace_id, active_workspace_id)
    rows = db.execute(text("""
        SELECT p.id, p.workspace_id, p.name, p.slug, p.created_at,
               COUNT(w.id) AS agent_count
        FROM projects p
        LEFT JOIN workflows w ON w.project_id = p.id
        WHERE p.workspace_id = :ws
        GROUP BY p.id
        ORDER BY p.created_at ASC
    """), {"ws": workspace_id}).fetchall()
    return [ProjectOut(id=str(r.id), workspace_id=str(r.workspace_id), name=r.name,
                       slug=r.slug or "", created_at=r.created_at, agent_count=r.agent_count or 0)
            for r in rows]


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    workspace_id: str,
    body: ProjectCreate,
    user_id: Annotated[str, Depends(get_user_id)],
    active_workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "developer")),
    db: Session = Depends(get_db),
):
    _enforce_workspace(workspace_id, active_workspace_id)
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Project name cannot be empty")

    project_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    name = body.name.strip()
    slug = _unique_slug(_slugify(name), workspace_id, db)
    db.execute(text("""
        INSERT INTO projects (id, workspace_id, name, slug, created_at)
        VALUES (:id, :ws, :name, :slug, :now)
    """), {"id": str(project_id), "ws": workspace_id, "name": name, "slug": slug, "now": now})
    db.commit()
    return ProjectOut(id=str(project_id), workspace_id=workspace_id,
                      name=name, slug=slug, created_at=now)


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
    slug = _unique_slug(_slugify(name), workspace_id, db, exclude_id=project_id)
    result = db.execute(text("""
        UPDATE projects SET name = :name, slug = :slug
        WHERE id = :id AND workspace_id = :ws
        RETURNING id
    """), {"name": name, "slug": slug, "id": project_id, "ws": workspace_id})
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Project not found")
    db.commit()

    row = db.execute(text("""
        SELECT p.id, p.workspace_id, p.name, p.slug, p.created_at, COUNT(w.id) AS agent_count
        FROM projects p LEFT JOIN workflows w ON w.project_id = p.id
        WHERE p.id = :id GROUP BY p.id
    """), {"id": project_id}).fetchone()
    return ProjectOut(id=str(row.id), workspace_id=str(row.workspace_id), name=row.name,
                      slug=row.slug or "", created_at=row.created_at, agent_count=row.agent_count or 0)


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


# ── Direct project lookup (no workspace cookie required) ─────────────────────

project_direct_router = APIRouter(prefix="/projects", tags=["workspace-projects"])


@project_direct_router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
):
    """Return a single project by ID. Workspace is derived from the project row —
    no X-Workspace-ID cookie required. Used by the project page to work correctly
    regardless of which workspace the browser cookie currently points to."""
    row = db.execute(text("""
        SELECT p.id, p.workspace_id, p.name, p.slug, p.created_at, COUNT(w.id) AS agent_count
        FROM projects p
        LEFT JOIN workflows w ON w.project_id = p.id
        WHERE p.id = :pid
        GROUP BY p.id
    """), {"pid": project_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    # Verify the requesting user is a member of the project's workspace.
    proj_ws = str(row.workspace_id)
    member = db.execute(
        text("SELECT 1 FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid"),
        {"ws": proj_ws, "uid": user_id},
    ).fetchone()
    if not member and user_id != "dev":
        raise HTTPException(status_code=403, detail="Not a member of this workspace")

    return ProjectOut(id=str(row.id), workspace_id=proj_ws, name=row.name,
                      slug=row.slug or "", created_at=row.created_at, agent_count=row.agent_count or 0)


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
    q = "SELECT id, actor_id, actor_email, actor_role, action, resource_type, resource_id, metadata AS meta, created_at FROM audit_log WHERE workspace_id = :ws"
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


# ── Workspace preferences ─────────────────────────────────────────────────────

_PREFERENCE_DEFAULTS = {
    "show_dry_run": False,
    "show_test_trigger": True,
    "watchdog_channel": "",
}


class PreferencesUpdate(BaseModel):
    show_dry_run: bool | None = None
    show_test_trigger: bool | None = None
    watchdog_channel: str | None = None  # Slack channel for watchdog alerts (e.g. #ops-alerts)


@preferences_router.get("")
def get_preferences(
    workspace_id: str,
    active_workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "developer", "security", "viewer")),
    db: Session = Depends(get_db),
):
    _enforce_workspace(workspace_id, active_workspace_id)
    from app.models.workspace import Workspace
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    stored = ws.preferences or {}
    return {**_PREFERENCE_DEFAULTS, **stored}


@preferences_router.patch("")
def update_preferences(
    workspace_id: str,
    body: PreferencesUpdate,
    active_workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "developer")),
    db: Session = Depends(get_db),
):
    _enforce_workspace(workspace_id, active_workspace_id)
    from app.models.workspace import Workspace
    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    current = dict(ws.preferences or {})
    patch = body.model_dump(exclude_none=True)
    current.update(patch)
    ws.preferences = current
    db.commit()
    return {**_PREFERENCE_DEFAULTS, **current}
