"""
Guard member endpoints — role sourced from workspace_users, token from guard_member_config.

GET    /guard/members?workspace_id                       — list members with role from workspace_users
PATCH  /guard/members/{clerk_user_id}?workspace_id       — update role in workspace_users
DELETE /guard/members/{clerk_user_id}?workspace_id       — remove from workspace_users
"""
import structlog

log = structlog.get_logger(__name__)

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, get_user_id, get_valid_roles
from app.core.database import get_db

router = APIRouter(prefix="/guard/members", tags=["guard-members"])


# ── Pydantic models ────────────────────────────────────────────────────────────

class MemberOut(BaseModel):
    clerk_user_id: str
    email: str
    role: str
    active: bool


class MemberPatch(BaseModel):
    role: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("", response_model=list[MemberOut])
def list_members(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _caller: str = Depends(get_user_id),
):
    """List all workspace members, joining guard_member_config for active status.
    Role is always from workspace_users.
    """
    rows = db.execute(
        text("""
            SELECT
                wu.clerk_user_id,
                wu.email,
                wu.role,
                COALESCE(gmc.active, true) AS active
            FROM workspace_users wu
            LEFT JOIN guard_member_config gmc
                   ON gmc.workspace_id = wu.workspace_id
                  AND gmc.clerk_user_id = wu.clerk_user_id
            WHERE wu.workspace_id = :ws
            ORDER BY wu.email ASC
        """),
        {"ws": workspace_id},
    ).fetchall()

    return [
        MemberOut(
            clerk_user_id=r.clerk_user_id,
            email=r.email,
            role=r.role,
            active=r.active,
        )
        for r in rows
    ]


@router.patch("/{clerk_user_id}", response_model=MemberOut)
def update_member_role(
    clerk_user_id: str,
    body: MemberPatch,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _caller: str = Depends(get_user_id),
):
    """Update a member's role in workspace_users (the single source of truth for role)."""
    valid = get_valid_roles(db)
    if body.role not in valid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid role '{body.role}'. Must be one of: {sorted(valid)}",
        )

    result = db.execute(
        text("""
            UPDATE workspace_users
            SET role = :role
            WHERE workspace_id = :ws AND clerk_user_id = :uid
            RETURNING clerk_user_id, email, role
        """),
        {"role": body.role, "ws": workspace_id, "uid": clerk_user_id},
    ).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Member not found in this workspace")

    db.commit()
    log.info("guard.member_role_updated", workspace_id=workspace_id, user_id=clerk_user_id, role=body.role)

    active_row = db.execute(
        text("""
            SELECT COALESCE(active, true) AS active
            FROM guard_member_config
            WHERE workspace_id = :ws AND clerk_user_id = :uid
            LIMIT 1
        """),
        {"ws": workspace_id, "uid": clerk_user_id},
    ).fetchone()

    return MemberOut(
        clerk_user_id=result.clerk_user_id,
        email=result.email,
        role=result.role,
        active=active_row.active if active_row else True,
    )


@router.delete("/{clerk_user_id}", status_code=204)
def remove_member(
    clerk_user_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _caller: str = Depends(get_user_id),
):
    """Remove a member from the workspace (and their guard_member_config entry)."""
    result = db.execute(
        text("""
            DELETE FROM workspace_users
            WHERE workspace_id = :ws AND clerk_user_id = :uid
            RETURNING clerk_user_id
        """),
        {"ws": workspace_id, "uid": clerk_user_id},
    ).fetchone()

    if not result:
        raise HTTPException(status_code=404, detail="Member not found in this workspace")

    # Also remove guard_member_config entry
    db.execute(
        text("""
            DELETE FROM guard_member_config
            WHERE workspace_id = :ws AND clerk_user_id = :uid
        """),
        {"ws": workspace_id, "uid": clerk_user_id},
    )

    db.commit()
    log.info("guard.member_removed", workspace_id=workspace_id, user_id=clerk_user_id)
