"""
Organizations — top-level billing/SSO unit.
One org contains one or more workspaces/teams.
"""
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_workspace_role
from app.core.database import get_db

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


@router.get("", response_model=list[OrgOut])
def list_organizations(
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
):
    """List all orgs the authenticated user belongs to (via their workspaces)."""
    rows = db.execute(text("""
        SELECT o.id, o.name, o.slug, o.created_at,
               COUNT(DISTINCT w.id) AS workspace_count
        FROM organizations o
        JOIN workspaces w ON w.org_id = o.id
        WHERE w.id IN (
            SELECT workspace_id FROM workspace_users WHERE clerk_user_id = :uid
            UNION
            SELECT id FROM workspaces WHERE owner_id = :uid
        )
        GROUP BY o.id
        ORDER BY o.created_at DESC
    """), {"uid": user_id}).fetchall()

    if rows:
        return [OrgOut(id=str(r.id), name=r.name, slug=r.slug,
                       created_at=r.created_at, workspace_count=r.workspace_count or 0)
                for r in rows]

    # Auto-create a default org and link the user's workspace to it
    workspace_row = db.execute(text("""
        SELECT id FROM workspaces
        WHERE id IN (
            SELECT workspace_id FROM workspace_users WHERE clerk_user_id = :uid
            UNION SELECT id FROM workspaces WHERE owner_id = :uid
        )
        ORDER BY created_at ASC LIMIT 1
    """), {"uid": user_id}).fetchone()

    org_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    slug = f"org-{str(org_id)[:8]}"
    db.execute(text("INSERT INTO organizations (id, name, slug, created_at) VALUES (:id, :name, :slug, :now)"),
               {"id": str(org_id), "name": "My Organization", "slug": slug, "now": now})
    if workspace_row:
        db.execute(text("UPDATE workspaces SET org_id = :org WHERE id = :ws"),
                   {"org": str(org_id), "ws": str(workspace_row.id)})
    db.commit()
    return [OrgOut(id=str(org_id), name="My Organization", slug=slug, created_at=now, workspace_count=1 if workspace_row else 0)]


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
    existing = db.execute(text("SELECT id FROM organizations WHERE slug = :slug"), {"slug": slug}).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Slug already taken")

    org_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    db.execute(text("""
        INSERT INTO organizations (id, name, slug, created_at)
        VALUES (:id, :name, :slug, :now)
    """), {"id": str(org_id), "name": body.name.strip(), "slug": slug, "now": now})
    db.commit()
    return OrgOut(id=str(org_id), name=body.name.strip(), slug=slug, created_at=now)


@router.get("/{org_id}", response_model=OrgOut)
def get_organization(
    org_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
):
    row = db.execute(text("""
        SELECT o.id, o.name, o.slug, o.created_at,
               COUNT(DISTINCT w.id) AS workspace_count
        FROM organizations o
        LEFT JOIN workspaces w ON w.org_id = o.id
        WHERE o.id = :id
        GROUP BY o.id
    """), {"id": org_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Organization not found")
    return OrgOut(id=str(row.id), name=row.name, slug=row.slug,
                  created_at=row.created_at, workspace_count=row.workspace_count or 0)


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
    result = db.execute(text(
        "UPDATE organizations SET name = :name WHERE id = :id RETURNING id"
    ), {"name": name, "id": org_id})
    if not result.fetchone():
        raise HTTPException(status_code=404, detail="Organization not found")
    db.commit()
    return get_organization(org_id, user_id, db)
