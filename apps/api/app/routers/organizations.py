"""
Organizations — top-level billing/SSO unit.
One org contains one or more workspaces/teams.
"""
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_workspace_role
from app.core.database import get_db
from app.models.organization import Organization
from app.models.workspace import Workspace
from app.models.workspace_user import WorkspaceUser

router = APIRouter(prefix="/organizations", tags=["organizations"])


class OrgOut(BaseModel):
    id: str
    name: str
    slug: str
    created_at: datetime
    workspace_count: int = 0


class OrgCreate(BaseModel):
    name: str
    slug: str


def _user_workspace_ids(db: Session, user_id: str) -> list:
    """Return all workspace IDs the user belongs to (member or owner)."""
    member_ids = (
        db.query(WorkspaceUser.workspace_id)
        .filter(WorkspaceUser.clerk_user_id == user_id)
        .subquery()
    )
    owner_ids = (
        db.query(Workspace.id)
        .filter(Workspace.owner_id == user_id)
        .subquery()
    )
    from sqlalchemy import union
    combined = union(
        db.query(WorkspaceUser.workspace_id).filter(WorkspaceUser.clerk_user_id == user_id),
        db.query(Workspace.id).filter(Workspace.owner_id == user_id),
    ).subquery()
    return combined


@router.get("", response_model=list[OrgOut])
def list_organizations(
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
):
    """List all orgs the authenticated user belongs to (via their workspaces)."""
    from sqlalchemy import func, union

    ws_ids_q = union(
        db.query(WorkspaceUser.workspace_id).filter(WorkspaceUser.clerk_user_id == user_id),
        db.query(Workspace.id).filter(Workspace.owner_id == user_id),
    ).subquery()

    rows = (
        db.query(Organization, func.count(Workspace.id.distinct()).label("workspace_count"))
        .join(Workspace, Workspace.org_id == Organization.id)
        .filter(Workspace.id.in_(db.query(ws_ids_q)))
        .group_by(Organization.id)
        .order_by(Organization.created_at.desc())
        .all()
    )

    if rows:
        return [
            OrgOut(
                id=str(org.id),
                name=org.name,
                slug=org.slug,
                created_at=org.created_at,
                workspace_count=count or 0,
            )
            for org, count in rows
        ]

    # Auto-create a default org and link the user's workspace to it
    workspace = (
        db.query(Workspace)
        .filter(Workspace.id.in_(db.query(ws_ids_q)))
        .order_by(Workspace.created_at.asc())
        .first()
    )

    now = datetime.now(timezone.utc)
    new_org_id = uuid.uuid4()
    slug = f"org-{str(new_org_id)[:8]}"
    org = Organization(id=new_org_id, name="My Organization", slug=slug, created_at=now)
    db.add(org)
    if workspace:
        workspace.org_id = new_org_id
    db.commit()
    return [OrgOut(id=str(new_org_id), name="My Organization", slug=slug, created_at=now, workspace_count=1 if workspace else 0)]


@router.post("", response_model=OrgOut, status_code=201)
def create_organization(
    body: OrgCreate,
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
):
    if not body.name.strip():
        raise HTTPException(status_code=422, detail="Organization name cannot be empty")
    if not body.slug.strip():
        raise HTTPException(status_code=422, detail="Slug cannot be empty")

    slug = body.slug.strip().lower()
    existing = db.query(Organization).filter(Organization.slug == slug).first()
    if existing:
        raise HTTPException(status_code=409, detail="Slug already taken")

    now = datetime.now(timezone.utc)
    new_org_id = uuid.uuid4()
    org = Organization(id=new_org_id, name=body.name.strip(), slug=slug, created_at=now)
    db.add(org)
    db.commit()
    return OrgOut(id=str(new_org_id), name=body.name.strip(), slug=slug, created_at=now)


@router.get("/{org_id}", response_model=OrgOut)
def get_organization(
    org_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
):
    from sqlalchemy import func

    row = (
        db.query(Organization, func.count(Workspace.id.distinct()).label("workspace_count"))
        .outerjoin(Workspace, Workspace.org_id == Organization.id)
        .filter(Organization.id == org_id)
        .group_by(Organization.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Organization not found")
    org, workspace_count = row
    return OrgOut(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        created_at=org.created_at,
        workspace_count=workspace_count or 0,
    )


@router.patch("/{org_id}", response_model=OrgOut)
def rename_organization(
    org_id: str,
    body: dict,
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be empty")
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    org.name = name
    db.commit()
    return get_organization(org_id, user_id, db)
