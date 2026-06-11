"""RBAC router — roles, permissions, and per-user permission resolution."""
import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.auth import get_user_id
from app.core.database import get_db
from app.models.rbac import Permission, Role
from app.models.workspace_user import WorkspaceUser

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

def _resolve_role(db: Session, workspace_id: str, user_id: str) -> str:
    """Resolve effective role from workspace_users. Returns 'viewer' if not a member."""
    row = (
        db.query(WorkspaceUser)
        .filter(
            WorkspaceUser.workspace_id == workspace_id,
            WorkspaceUser.clerk_user_id == user_id,
        )
        .first()
    )
    return row.role if row else "viewer"


@me_router.get("/permissions", response_model=PermissionSet)
def get_my_permissions(
    workspace_id: Annotated[str, Query()],
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
) -> PermissionSet:
    """Return the calling user's resolved role and permission names for a workspace."""
    role = _resolve_role(db, workspace_id, user_id)

    system_role = (
        db.query(Role)
        .filter(Role.name == role, Role.workspace_id.is_(None))
        .first()
    )

    if system_role:
        permission_names = sorted(p.name for p in system_role.permissions)
    else:
        permission_names = []

    log.info("rbac.permissions_resolved", workspace_id=workspace_id, role=role, count=len(permission_names))
    return PermissionSet(role=role, permissions=permission_names)
