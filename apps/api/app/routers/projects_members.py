"""Project member + invite management endpoints (split from projects.py).

Second link of the route-registration chain (see projects_core).
"""
import uuid
from datetime import datetime, timezone
from typing import Annotated
import structlog
from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.auth import get_user_id, get_workspace_id, require_permission, get_clerk_user_email, get_clerk_user_info, find_clerk_user_id_by_email, get_role_description
from app.core.config import settings
from app.core.database import get_db
from app.core.email import send_template_email, APP_URL
from app.routers.projects_core import (
    InviteOut,
    MemberAdd,
    MemberOut,
    MemberWorkspaceOut,
    _audit,
    _seed_starter_policies,
    _send_clerk_invite,
    router,
)

log = structlog.get_logger("app.routers.projects")


# ---------------------------------------------------------------------------
# Member management
# ---------------------------------------------------------------------------

@router.get("/{project_id}/members", response_model=list[MemberOut])
def list_members(
    project_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _: Annotated[str, Depends(require_permission("platform.members.manage"))],
    db: Session = Depends(get_db),
):
    if project_id != workspace_id:
        raise HTTPException(status_code=404, detail="Project not found")
    rows = db.execute(text("""
        SELECT clerk_user_id, role, invited_by, joined_at
        FROM workspace_users
        WHERE workspace_id = :ws
        ORDER BY joined_at
    """), {"ws": workspace_id}).fetchall()
    names = {}
    if settings.auth_mode == "proxy":
        from app.modules.auth.console.profiles import member_names
        names = member_names(db, [r.clerk_user_id for r in rows])
    out = []
    for r in rows:
        info = ({"email": None, "name": names.get(r.clerk_user_id)}
                if settings.auth_mode == "proxy" else get_clerk_user_info(r.clerk_user_id))
        out.append(MemberOut(
            clerk_user_id=r.clerk_user_id, role=r.role,
            invited_by=r.invited_by, joined_at=r.joined_at,
            email=info["email"], name=info["name"],
        ))
    return out


@router.get("/{project_id}/my-role")
def get_my_role(
    project_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    db: Session = Depends(get_db),
):
    if project_id != workspace_id:
        raise HTTPException(status_code=404, detail="Project not found")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    row = db.execute(text("""
        SELECT role FROM workspace_users
        WHERE workspace_id = :ws AND clerk_user_id = :uid
    """), {"ws": workspace_id, "uid": user_id}).fetchone()
    if not row:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    return {"role": row.role}

@router.post("/{project_id}/guard/install", status_code=200)
def install_guard(
    project_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    db: Session = Depends(get_db),
):
    """Idempotent Guard install — creates guard_config + caller's guard_member_config if absent."""
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    import secrets as _secrets
    now = datetime.now(timezone.utc)
    invite_code = _secrets.token_urlsafe(16)
    db.execute(text("""
        INSERT INTO guard_config (workspace_id, invite_code, created_at)
        VALUES (:ws, :invite_code, :now)
        ON CONFLICT (workspace_id) DO NOTHING
    """), {"ws": workspace_id, "invite_code": invite_code, "now": now})
    _seed_starter_policies(db, uuid.UUID(workspace_id), now)
    db.execute(text("""
        INSERT INTO guard_member_config (workspace_id, clerk_user_id, member_token, active, joined_at)
        VALUES (:ws, :uid, :token, true, :now)
        ON CONFLICT (workspace_id, clerk_user_id) DO NOTHING
    """), {"ws": workspace_id, "uid": user_id, "token": _secrets.token_urlsafe(24), "now": now})
    db.commit()
    return {"installed": True}


@router.get("/{project_id}/members/{clerk_user_id}/workspaces", response_model=list[MemberWorkspaceOut])
def get_member_workspaces(
    project_id: str,
    clerk_user_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _: Annotated[str, Depends(require_permission("platform.members.manage"))],
    db: Session = Depends(get_db),
):
    if project_id != workspace_id:
        raise HTTPException(status_code=404, detail="Project not found")
    rows = db.execute(text("""
        SELECT w.id, w.name, wu.role, wu.joined_at
        FROM workspace_users wu
        JOIN workspaces w ON w.id = wu.workspace_id
        WHERE wu.clerk_user_id = :uid
        ORDER BY wu.joined_at
    """), {"uid": clerk_user_id}).fetchall()
    return [
        MemberWorkspaceOut(id=str(r.id), name=r.name, role=r.role, joined_at=r.joined_at)
        for r in rows
    ]


@router.post("/{project_id}/members", status_code=201)
def add_member(
    project_id: str,
    body: MemberAdd,
    user_id: Annotated[str, Depends(get_user_id)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    actor_role: Annotated[str, Depends(require_permission("platform.members.manage"))],
    db: Session = Depends(get_db),
):
    if project_id != workspace_id:
        raise HTTPException(status_code=404, detail="Project not found")
    from app.core.auth import get_valid_roles
    if body.role not in get_valid_roles(db):
        raise HTTPException(status_code=422, detail=f"Invalid role '{body.role}'")
    if settings.auth_mode == "proxy":
        from app.modules.auth.console.models import ConsoleIdentityMapping
        if body.email:
            raise HTTPException(422, "Proxy console users require explicit identity provisioning, not email invitations")
        if not db.query(ConsoleIdentityMapping).filter_by(user_id=body.clerk_user_id, active=True).first():
            raise HTTPException(422, "Console identity is not provisioned")
    now = datetime.now(timezone.utc)

    # Email invite path — store as pending invite
    if body.email:
        email = body.email.strip().lower()

        # Check if this email already belongs to an existing workspace member
        existing_clerk_id = find_clerk_user_id_by_email(email)
        if existing_clerk_id:
            existing_member = db.execute(text("""
                SELECT clerk_user_id FROM workspace_users
                WHERE workspace_id = :ws AND clerk_user_id = :uid
            """), {"ws": workspace_id, "uid": existing_clerk_id}).fetchone()
            if existing_member:
                raise HTTPException(status_code=409, detail="This person is already a member of the workspace")

        existing_invite = db.execute(text("""
            SELECT id FROM workspace_invites
            WHERE workspace_id = :ws AND invited_email = :email AND accepted_at IS NULL
        """), {"ws": workspace_id, "email": email}).fetchone()
        if existing_invite:
            raise HTTPException(status_code=409, detail="An invite for this email is already pending")
        invite_id = db.execute(text("""
            INSERT INTO workspace_invites (workspace_id, invited_email, role, invited_by, created_at)
            VALUES (:ws, :email, :role, :invited_by, :now)
            ON CONFLICT (workspace_id, invited_email)
            DO UPDATE SET role = EXCLUDED.role,
                          invited_by = EXCLUDED.invited_by,
                          created_at = EXCLUDED.created_at,
                          accepted_at = NULL
            RETURNING id
        """), {"ws": workspace_id, "email": email, "role": body.role,
               "invited_by": user_id, "now": now}).fetchone()[0]
        inviter_email = get_clerk_user_email(user_id)
        _audit(db, workspace_id=workspace_id, actor_id=user_id,
               actor_email=inviter_email, actor_role=actor_role,
               action="member.invited", resource_type="invite",
               resource_id=email, meta={"role": body.role, "invite_id": str(invite_id)})
        db.commit()

        # Send Clerk org invitation — fire-and-forget on top of our DB record
        _send_clerk_invite(db, workspace_id, email, body.role, invite_id=str(invite_id))

        # Resolve workspace name for the notification
        ws_row = db.execute(text("SELECT name FROM workspaces WHERE id = :id"), {"id": workspace_id}).fetchone()
        workspace_name = ws_row.name if ws_row else "your workspace"

        # Guard is org-level — check if any workspace in the org has Guard installed
        guard_row = db.execute(
            text("""
                SELECT gc.workspace_id FROM guard_config gc
                JOIN workspaces w ON w.id = gc.workspace_id
                WHERE w.org_id = (SELECT org_id FROM workspaces WHERE id::text = :ws)
                   OR gc.workspace_id::text = :ws
                LIMIT 1
            """),
            {"ws": workspace_id},
        ).fetchone()
        guard_invite_cmd = "conduct guard sync" if guard_row else ""

        email_sent = send_template_email(
            slug="workspace_invite",
            to=email,
            context={
                "workspace_name": workspace_name,
                "invited_by_email": inviter_email or "",
                "role": body.role,
                "role_description": get_role_description(body.role, db),
                "app_url": APP_URL,
                "workspace_id": workspace_id,
                "guard_invite_cmd": guard_invite_cmd,
            },
            workspace_id=workspace_id,
            db=db,
        )
        if not email_sent:
            log.warning("invite.email_not_sent", email=email, reason="no email credential configured")

        return InviteOut(id=str(invite_id), invited_email=email, role=body.role,
                         invited_by=user_id, created_at=now, email_sent=email_sent)

    # Direct add path — clerk_user_id must be provided
    if not body.clerk_user_id:
        raise HTTPException(status_code=422, detail="Provide either email or clerk_user_id")
    existing = db.execute(text("""
        SELECT clerk_user_id FROM workspace_users
        WHERE workspace_id = :ws AND clerk_user_id = :uid
    """), {"ws": workspace_id, "uid": body.clerk_user_id}).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="User is already a member")
    db.execute(text("""
        INSERT INTO workspace_users (workspace_id, clerk_user_id, role, invited_by, joined_at)
        VALUES (:ws, :uid, :role, :invited_by, :now)
    """), {"ws": workspace_id, "uid": body.clerk_user_id,
           "role": body.role, "invited_by": user_id, "now": now})
    _audit(db, workspace_id=workspace_id, actor_id=user_id,
           actor_email=None, actor_role=actor_role,
           action="member.added", resource_type="member",
           resource_id=body.clerk_user_id, meta={"role": body.role})
    # Provision Guard membership if Guard is installed for this workspace
    guard_config = db.execute(
        text("SELECT workspace_id FROM guard_config WHERE workspace_id = :ws LIMIT 1"),
        {"ws": workspace_id},
    ).fetchone()
    if guard_config:
        import secrets as _secrets
        db.execute(text("""
            INSERT INTO guard_member_config (workspace_id, clerk_user_id, member_token, active, joined_at)
            VALUES (:ws, :uid, :token, true, :now)
            ON CONFLICT (workspace_id, clerk_user_id) DO NOTHING
        """), {"ws": workspace_id, "uid": body.clerk_user_id,
               "token": _secrets.token_urlsafe(24), "now": now})
    db.commit()
    return MemberOut(clerk_user_id=body.clerk_user_id, role=body.role,
                     invited_by=user_id, joined_at=now)


@router.get("/{project_id}/invites", response_model=list[InviteOut])
def list_invites(
    project_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _: Annotated[str, Depends(require_permission("platform.members.manage"))],
    db: Session = Depends(get_db),
):
    if project_id != workspace_id:
        raise HTTPException(status_code=404, detail="Project not found")
    rows = db.execute(text("""
        SELECT id, invited_email, role, invited_by, created_at
        FROM workspace_invites
        WHERE workspace_id = :ws AND accepted_at IS NULL
        ORDER BY created_at DESC
    """), {"ws": workspace_id}).fetchall()
    return [InviteOut(id=str(r.id), invited_email=r.invited_email, role=r.role,
                      invited_by=r.invited_by, created_at=r.created_at) for r in rows]


@router.delete("/{project_id}/invites/{invite_id}", status_code=204)
def cancel_invite(
    project_id: str,
    invite_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    actor_role: Annotated[str, Depends(require_permission("platform.members.manage"))],
    db: Session = Depends(get_db),
):
    if project_id != workspace_id:
        raise HTTPException(status_code=404, detail="Project not found")
    result = db.execute(text("""
        DELETE FROM workspace_invites
        WHERE id = :id AND workspace_id = :ws AND accepted_at IS NULL
        RETURNING id, invited_email, role, clerk_invitation_id
    """), {"id": invite_id, "ws": workspace_id})
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Invite not found or already accepted")
    _audit(db, workspace_id=workspace_id, actor_id=user_id,
           actor_email=None, actor_role=actor_role,
           action="invite.cancelled", resource_type="invite",
           resource_id=invite_id, meta={"invited_email": row.invited_email, "role": row.role})
    db.commit()

    # Revoke Clerk invitation if we have one — best-effort, after our DB commit
    if row.clerk_invitation_id and settings.clerk_secret_key:
        ws_org = db.execute(
            text("SELECT clerk_org_id FROM workspaces WHERE id = :id"),
            {"id": workspace_id},
        ).fetchone()
        if ws_org and ws_org.clerk_org_id:
            import httpx as _httpx
            try:
                _httpx.post(
                    f"https://api.clerk.com/v1/organizations/{ws_org.clerk_org_id}"
                    f"/invitations/{row.clerk_invitation_id}/revoke",
                    headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
                    timeout=5,
                )
            except Exception as e:
                log.warning("clerk.invite_revoke_failed",
                            clerk_invitation_id=row.clerk_invitation_id, error=str(e))


@router.patch("/{project_id}/members/{clerk_user_id}")
def update_member_role(
    project_id: str,
    clerk_user_id: str,
    body: dict,
    user_id: Annotated[str, Depends(get_user_id)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    actor_role: Annotated[str, Depends(require_permission("platform.members.manage"))],
    db: Session = Depends(get_db),
):
    if project_id != workspace_id:
        raise HTTPException(status_code=404, detail="Project not found")
    new_role = body.get("role", "")
    from app.core.auth import get_valid_roles
    if new_role not in get_valid_roles(db):
        raise HTTPException(status_code=422, detail=f"Invalid role '{new_role}'")
    if clerk_user_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot change your own role")
    old_row = db.execute(text("""
        SELECT role FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid
    """), {"ws": workspace_id, "uid": clerk_user_id}).fetchone()
    if not old_row:
        raise HTTPException(status_code=404, detail="Member not found")
    old_role = old_row.role
    db.execute(text("""
        UPDATE workspace_users SET role = :role
        WHERE workspace_id = :ws AND clerk_user_id = :uid
    """), {"role": new_role, "ws": workspace_id, "uid": clerk_user_id})
    _audit(db, workspace_id=workspace_id, actor_id=user_id,
           actor_email=None, actor_role=actor_role,
           action="member.role_changed", resource_type="member",
           resource_id=clerk_user_id, meta={"from_role": old_role, "to_role": new_role})
    db.commit()
    return {"clerk_user_id": clerk_user_id, "role": new_role}


@router.delete("/{project_id}/members/{clerk_user_id}", status_code=204)
def remove_member(
    project_id: str,
    clerk_user_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    actor_role: Annotated[str, Depends(require_permission("platform.members.manage"))],
    db: Session = Depends(get_db),
):
    if project_id != workspace_id:
        raise HTTPException(status_code=404, detail="Project not found")
    if clerk_user_id == user_id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")
    removed = db.execute(text("""
        DELETE FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid
        RETURNING role
    """), {"ws": workspace_id, "uid": clerk_user_id}).fetchone()
    if not removed:
        raise HTTPException(status_code=404, detail="Member not found")
    _audit(db, workspace_id=workspace_id, actor_id=user_id,
           actor_email=None, actor_role=actor_role,
           action="member.removed", resource_type="member",
           resource_id=clerk_user_id, meta={"role": removed.role})
    db.commit()

    # Remove from Clerk org — best-effort, after our DB commit
    if settings.clerk_secret_key:
        ws = db.execute(
            text("SELECT clerk_org_id FROM workspaces WHERE id = :id"),
            {"id": workspace_id},
        ).fetchone()
        if ws and ws.clerk_org_id:
            import httpx as _httpx
            try:
                _httpx.delete(
                    f"https://api.clerk.com/v1/organizations/{ws.clerk_org_id}"
                    f"/memberships/{clerk_user_id}",
                    headers={"Authorization": f"Bearer {settings.clerk_secret_key}"},
                    timeout=5,
                )
            except Exception as e:
                log.warning("clerk.member_remove_failed", user_id=clerk_user_id, error=str(e))
