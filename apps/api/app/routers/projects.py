"""
Projects (workspaces) CRUD + template listing.

A "project" is a workspace owned by a single user. Workflows and credentials
are scoped to a project. Google sign-in is the access gate — all signed-in
users get immediate access with no waitlist.
"""
import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_user_id
from app.core.config import settings
from app.core.database import get_db

router = APIRouter(prefix="/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class TemplateOut(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    default_mode: str


class ProjectOut(BaseModel):
    id: str
    name: str
    owner_id: str
    is_approved: bool
    created_at: datetime
    workflow_count: int = 0


class ProjectCreate(BaseModel):
    name: str
    template_id: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/templates", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db)):
    rows = db.execute(text(
        "SELECT id, slug, name, description, default_mode FROM project_templates ORDER BY name"
    )).fetchall()
    return [TemplateOut(id=str(r.id), slug=r.slug, name=r.name, description=r.description, default_mode=r.default_mode) for r in rows]


@router.get("", response_model=list[ProjectOut])
def list_projects(
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
):
    rows = db.execute(text("""
        SELECT w.id, w.name, w.owner_id, w.is_approved, w.created_at,
               COUNT(wf.id) AS workflow_count
        FROM workspaces w
        LEFT JOIN workflows wf ON wf.workspace_id = w.id
        WHERE w.owner_id = :owner_id
        GROUP BY w.id
        ORDER BY w.created_at DESC
    """), {"owner_id": user_id}).fetchall()

    # Auto-register new users with an approved workspace — Google auth is the gate
    if not rows:
        project_id, now = uuid.uuid4(), datetime.utcnow()
        db.execute(text("""
            INSERT INTO workspaces (id, name, owner_id, plan, is_approved, created_at, updated_at)
            VALUES (:id, 'My Workspace', :owner_id, 'free', true, :now, :now)
        """), {"id": str(project_id), "owner_id": user_id, "now": now})
        db.commit()
        return [ProjectOut(id=str(project_id), name="My Workspace", owner_id=user_id,
                           is_approved=True, created_at=now, workflow_count=0)]

    return [
        ProjectOut(
            id=str(r.id), name=r.name, owner_id=r.owner_id,
            is_approved=r.is_approved, created_at=r.created_at,
            workflow_count=r.workflow_count or 0,
        )
        for r in rows
    ]


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    body: ProjectCreate,
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Project name cannot be empty")

    project_id, now = uuid.uuid4(), datetime.utcnow()
    db.execute(text("""
        INSERT INTO workspaces (id, name, owner_id, plan, is_approved, created_at, updated_at)
        VALUES (:id, :name, :owner_id, 'free', true, :now, :now)
    """), {"id": str(project_id), "name": body.name.strip(), "owner_id": user_id, "now": now})

    if body.template_id:
        tmpl = db.execute(text(
            "SELECT name, default_mode, nodes, edges FROM project_templates WHERE id = :id"
        ), {"id": body.template_id}).fetchone()
        if tmpl:
            _seed_workflow_from_template(db, project_id, tmpl)

    db.commit()
    return ProjectOut(id=str(project_id), name=body.name.strip(), owner_id=user_id,
                      is_approved=True, created_at=now,
                      workflow_count=1 if body.template_id else 0)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
):
    row = db.execute(text("SELECT owner_id FROM workspaces WHERE id = :id"), {"id": project_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    if row.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Not your project")

    db.execute(text("""
        DELETE FROM run_events WHERE run_id IN (
            SELECT r.id FROM runs r
            JOIN workflow_versions wv ON wv.id = r.workflow_version_id
            JOIN workflows w ON w.id = wv.workflow_id
            WHERE w.workspace_id = :pid
        )
    """), {"pid": project_id})
    db.execute(text("""
        DELETE FROM runs WHERE workflow_version_id IN (
            SELECT wv.id FROM workflow_versions wv
            JOIN workflows w ON w.id = wv.workflow_id
            WHERE w.workspace_id = :pid
        )
    """), {"pid": project_id})
    db.execute(text("DELETE FROM workflow_versions WHERE workflow_id IN (SELECT id FROM workflows WHERE workspace_id = :pid)"), {"pid": project_id})
    db.execute(text("DELETE FROM workflows WHERE workspace_id = :pid"), {"pid": project_id})
    db.execute(text("DELETE FROM integrations WHERE workspace_id = :pid"), {"pid": project_id})
    db.execute(text("DELETE FROM workspaces WHERE id = :pid"), {"pid": project_id})
    db.commit()


# ---------------------------------------------------------------------------
# Admin — approve a user by owner_id or workspace id
# Protected by X-Admin-Secret header matching ADMIN_SECRET env var
# ---------------------------------------------------------------------------

@router.post("/admin/approve", status_code=200)
def admin_approve(
    body: dict,
    x_admin_secret: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
):
    if not settings.admin_secret or x_admin_secret != settings.admin_secret:
        raise HTTPException(status_code=403, detail="Invalid admin secret")

    owner_id = body.get("owner_id")
    workspace_id = body.get("workspace_id")

    if not owner_id and not workspace_id:
        raise HTTPException(status_code=422, detail="Provide owner_id or workspace_id")

    if owner_id:
        result = db.execute(text(
            "UPDATE workspaces SET is_approved = true WHERE owner_id = :oid RETURNING id, name"
        ), {"oid": owner_id})
    else:
        result = db.execute(text(
            "UPDATE workspaces SET is_approved = true WHERE id = :wid RETURNING id, name"
        ), {"wid": workspace_id})

    rows = result.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="No workspaces found")

    db.commit()
    return {"approved": [{"id": str(r.id), "name": r.name} for r in rows]}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_workflow_from_template(db, project_id: uuid.UUID, tmpl) -> None:
    wf_id = uuid.uuid4()
    graph = {"nodes": tmpl.nodes, "edges": tmpl.edges}

    db.execute(text("""
        INSERT INTO workflows (id, workspace_id, name, default_mode)
        VALUES (:id, :ws, :name, :mode)
    """), {"id": str(wf_id), "ws": str(project_id), "name": tmpl.name, "mode": tmpl.default_mode})

    version_id = db.execute(text("""
        INSERT INTO workflow_versions (workflow_id, graph)
        VALUES (:wf, cast(:graph as jsonb))
        RETURNING id
    """), {"wf": str(wf_id), "graph": json.dumps(graph)}).fetchone()[0]

    db.execute(text("UPDATE workflows SET current_version_id = :vid WHERE id = :id"),
               {"vid": str(version_id), "id": str(wf_id)})
