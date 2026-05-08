"""
Projects (workspaces) CRUD + template listing.

A "project" is a workspace owned by a single user. Workflows and credentials
are scoped to a project.
"""
import json
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_user_id
from app.core.database import get_db
from app.models.workspace import Workspace

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
    rows = db.execute(text("SELECT id, slug, name, description, default_mode FROM project_templates ORDER BY name")).fetchall()
    return [TemplateOut(id=str(r.id), slug=r.slug, name=r.name, description=r.description, default_mode=r.default_mode) for r in rows]


@router.get("", response_model=list[ProjectOut])
def list_projects(
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
):
    rows = db.execute(text("""
        SELECT w.id, w.name, w.owner_id, w.created_at,
               COUNT(wf.id) AS workflow_count
        FROM workspaces w
        LEFT JOIN workflows wf ON wf.workspace_id = w.id
        WHERE w.owner_id = :owner_id
        GROUP BY w.id
        ORDER BY w.created_at DESC
    """), {"owner_id": user_id}).fetchall()

    return [
        ProjectOut(
            id=str(r.id),
            name=r.name,
            owner_id=r.owner_id,
            created_at=r.created_at,
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

    project_id = uuid.uuid4()
    now = datetime.utcnow()

    db.execute(text("""
        INSERT INTO workspaces (id, name, owner_id, plan, created_at, updated_at)
        VALUES (:id, :name, :owner_id, 'free', :now, :now)
    """), {"id": str(project_id), "name": body.name.strip(), "owner_id": user_id, "now": now})

    # Seed workflows from template if requested
    if body.template_id:
        tmpl = db.execute(text(
            "SELECT name, default_mode, nodes, edges FROM project_templates WHERE id = :id"
        ), {"id": body.template_id}).fetchone()

        if tmpl:
            _seed_workflow_from_template(db, project_id, tmpl)

    db.commit()

    return ProjectOut(id=str(project_id), name=body.name.strip(), owner_id=user_id, created_at=now, workflow_count=1 if body.template_id else 0)


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

    # Cascade: runs → run_events, workflow_versions, workflows, integrations
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
