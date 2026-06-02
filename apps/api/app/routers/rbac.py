"""RBAC router — roles, permissions, and per-user permission resolution."""
import secrets
import uuid
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_user_id
from app.core.database import get_db
from app.models.rbac import Permission, Role

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/rbac", tags=["rbac"])
me_router = APIRouter(prefix="/me", tags=["me"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class RoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str | None
    is_system: bool


class PermissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    description: str | None


class PermissionSet(BaseModel):
    role: str
    permissions: list[str]


# ---------------------------------------------------------------------------
# /rbac routes
# ---------------------------------------------------------------------------

@router.get("/roles", response_model=list[RoleOut])
def list_roles(db: Session = Depends(get_db)) -> list[Role]:
    """Return all system roles (workspace_id IS NULL) with their permissions."""
    return db.query(Role).filter(Role.workspace_id.is_(None)).order_by(Role.name).all()


@router.get("/permissions", response_model=list[PermissionOut])
def list_permissions(db: Session = Depends(get_db)) -> list[Permission]:
    """Return every permission in the system."""
    return db.query(Permission).order_by(Permission.name).all()


# ---------------------------------------------------------------------------
# /me/permissions
# ---------------------------------------------------------------------------

def _resolve_and_provision(db: Session, workspace_id: str, user_id: str, user_email: str | None) -> str:
    """Resolve effective role and auto-provision guard_members on first login.

    Resolution order:
    1. guard_members — already provisioned
    2. workspace_users — first login; auto-upsert into guard_members
    3. Default: "viewer" (no auto-provision — user has no platform membership)
    """
    # Resolve team — workspace_id FK first, conductai_org_id fallback for old teams
    team_row = db.execute(
        text("""
            SELECT id FROM guard_teams
            WHERE workspace_id = :ws
            UNION
            SELECT gt.id FROM guard_teams gt
            JOIN workspaces w ON w.owner_id = gt.conductai_org_id
            WHERE w.id = :ws AND gt.workspace_id IS NULL
            LIMIT 1
        """),
        {"ws": workspace_id},
    ).fetchone()
    if not team_row:
        return "viewer"
    team_id = str(team_row.id)

    # 1. Already a Guard member
    guard_row = db.execute(
        text("""
            SELECT role FROM guard_members
            WHERE team_id = :tid AND user_id = :uid AND active = true
            LIMIT 1
        """),
        {"tid": team_id, "uid": user_id},
    ).fetchone()
    if guard_row:
        return guard_row.role

    # 2. Platform member — auto-provision into guard_members
    ws_row = db.execute(
        text("""
            SELECT role, email FROM workspace_users
            WHERE workspace_id = :ws AND clerk_user_id = :uid
            LIMIT 1
        """),
        {"ws": workspace_id, "uid": user_id},
    ).fetchone()

    if ws_row:
        role = ws_row.role
        email = user_email or ws_row.email or f"{user_id}@unknown"
        existing = db.execute(
            text("SELECT id FROM guard_members WHERE team_id = :tid AND email = :email LIMIT 1"),
            {"tid": team_id, "email": email},
        ).fetchone()
        if not existing:
            db.execute(
                text("""
                    INSERT INTO guard_members (id, team_id, user_id, email, role, active, joined_at, member_token)
                    VALUES (:id, :tid, :uid, :email, :role, true, :now, :token)
                """),
                {
                    "id": str(uuid.uuid4()),
                    "tid": team_id,
                    "uid": user_id,
                    "email": email,
                    "role": role,
                    "now": datetime.now(timezone.utc),
                    "token": secrets.token_urlsafe(32),
                },
            )
            db.commit()
            log.info("rbac.guard_member_provisioned", workspace_id=workspace_id, user_id=user_id, role=role)
        return role

    # 3. No platform membership
    return "viewer"


@me_router.get("/permissions", response_model=PermissionSet)
def get_my_permissions(
    workspace_id: Annotated[str, Query()],
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
    email: str | None = Query(default=None),
) -> PermissionSet:
    """Return the calling user's resolved role and permission names for a workspace.
    Auto-provisions guard_members on first visit if the user is a workspace member.
    """
    role = _resolve_and_provision(db, workspace_id, user_id, user_email=email)

    rows = db.execute(
        text("""
            SELECT p.name
            FROM permissions p
            JOIN role_permissions rp ON rp.permission_id = p.id
            JOIN roles r ON r.id = rp.role_id
            WHERE r.name = :role
              AND r.workspace_id IS NULL
            ORDER BY p.name
        """),
        {"role": role},
    ).fetchall()

    permission_names = [row.name for row in rows]
    log.info("rbac.permissions_resolved", workspace_id=workspace_id, role=role, count=len(permission_names))
    return PermissionSet(role=role, permissions=permission_names)
