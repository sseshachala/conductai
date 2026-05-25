"""
Environments CRUD — per-workspace credential scoping.
GET    /environments                  — list environments for the workspace
POST   /environments                  — create environment
DELETE /environments/{env_id}         — delete environment (nullifies agent assignments)
"""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_workspace_role
from app.core.database import get_db
from app.models.environment import Environment
from app.models.integration import Integration
from app.models.workflow import Workflow

router = APIRouter(prefix="/environments", tags=["environments"])


class EnvironmentCreate(BaseModel):
    name: str


class EnvironmentOut(BaseModel):
    id: str
    name: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_row(cls, row: Environment) -> "EnvironmentOut":
        return cls(id=str(row.id), name=row.name, created_at=row.created_at)


@router.get("", response_model=list[EnvironmentOut])
def list_environments(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    rows = (
        db.query(Environment)
        .filter(Environment.workspace_id == workspace_id)
        .order_by(Environment.created_at)
        .all()
    )
    return [EnvironmentOut.from_orm_row(r) for r in rows]


@router.post("", response_model=EnvironmentOut, status_code=201)
def create_environment(
    body: EnvironmentCreate,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor")),
):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="name must not be empty")

    existing = (
        db.query(Environment)
        .filter(Environment.workspace_id == workspace_id, Environment.name == name)
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail=f"Environment '{name}' already exists")

    env = Environment(workspace_id=workspace_id, name=name)
    db.add(env)
    db.commit()
    db.refresh(env)
    return EnvironmentOut.from_orm_row(env)


@router.delete("/{env_id}", status_code=204)
def delete_environment(
    env_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    env = (
        db.query(Environment)
        .filter(Environment.id == env_id, Environment.workspace_id == workspace_id)
        .first()
    )
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")

    # Block deletion if any workflows are still assigned to this environment
    agents = (
        db.query(Workflow)
        .filter(Workflow.environment_id == env_id)
        .all()
    )
    if agents:
        names = ", ".join(a.name for a in agents)
        raise HTTPException(
            status_code=409,
            detail=f"Remove this environment from {len(agents)} agent(s) first: {names}",
        )

    # Delete integrations scoped to this environment, then delete the env
    db.query(Integration).filter(Integration.environment_id == env_id).delete(synchronize_session=False)
    db.delete(env)
    db.commit()
