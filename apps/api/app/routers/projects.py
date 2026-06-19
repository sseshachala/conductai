"""
Projects (workspaces) CRUD + template listing + member management.

A "project" is a workspace. Users belong to workspaces via workspace_users
(many-to-many with per-workspace roles). All signed-in users get immediate
access — the workspace_users table is the access gate.
"""
import hmac
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

import structlog
log = structlog.get_logger(__name__)

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_permission, get_clerk_user_email, get_clerk_user_info, find_clerk_user_id_by_email, get_role_description
from app.core.config import settings
from app.core.database import get_db
from app.core.email import send_template_email, APP_URL
from app.models.audit_log import AuditLog

router = APIRouter(prefix="/projects", tags=["projects"])


def _audit(db, *, workspace_id: str, actor_id: str, actor_email: str | None,
           actor_role: str | None, action: str, resource_type: str,
           resource_id: str | None = None, meta: dict | None = None) -> None:
    db.add(AuditLog(
        workspace_id=workspace_id,
        actor_id=actor_id,
        actor_email=actor_email,
        actor_role=actor_role,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        meta=meta,
    ))


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
    project_type: str = "user"
    security_finding_id: str | None = None


class ProjectCreate(BaseModel):
    name: str
    template_id: str | None = None


class MemberOut(BaseModel):
    clerk_user_id: str
    role: str
    invited_by: str | None
    joined_at: datetime
    email: str | None = None
    name: str | None = None


class MemberAdd(BaseModel):
    clerk_user_id: str | None = None   # direct add (existing user)
    email: str | None = None           # invite by email (pending until login)
    role: str


class MemberWorkspaceOut(BaseModel):
    id: str
    name: str
    role: str
    joined_at: datetime


class InviteOut(BaseModel):
    id: str
    invited_email: str
    role: str
    invited_by: str | None
    created_at: datetime
    email_sent: bool = True


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/templates", response_model=list[TemplateOut])
def list_templates(db: Session = Depends(get_db)):
    rows = db.execute(text(
        "SELECT id, slug, name, description, default_mode FROM project_templates ORDER BY name"
    )).fetchall()
    return [TemplateOut(id=str(r.id), slug=r.slug, name=r.name, description=r.description, default_mode=r.default_mode) for r in rows]


def _accept_pending_invites(user_id: str, db: Session) -> None:
    """Resolve any email-based pending invites for the authenticated user on first login."""
    email = get_clerk_user_email(user_id)
    if not email:
        return
    now = datetime.now(timezone.utc)
    invites = db.execute(text("""
        SELECT id, workspace_id, role, invited_by FROM workspace_invites
        WHERE invited_email = :email AND accepted_at IS NULL
    """), {"email": email}).fetchall()
    for inv in invites:
        ws_id = str(inv.workspace_id)
        db.execute(text("""
            INSERT INTO workspace_users (workspace_id, clerk_user_id, role, invited_by, joined_at)
            VALUES (:ws, :uid, :role, :invited_by, :now)
            ON CONFLICT DO NOTHING
        """), {"ws": ws_id, "uid": user_id,
               "role": inv.role, "invited_by": inv.invited_by, "now": now})
        db.execute(text("UPDATE workspace_invites SET accepted_at = :now WHERE id = :id"),
                   {"now": now, "id": str(inv.id)})
        # Auto-enroll in Guard if the workspace has Guard installed
        guard_installed = db.execute(
            text("SELECT 1 FROM guard_config WHERE workspace_id::text = :ws LIMIT 1"),
            {"ws": ws_id},
        ).fetchone()
        if guard_installed:
            import secrets as _secrets
            db.execute(text("""
                INSERT INTO guard_member_config (workspace_id, clerk_user_id, member_token, active, joined_at)
                VALUES (:ws, :user_id, :token, true, :now)
                ON CONFLICT (workspace_id, clerk_user_id) DO NOTHING
            """), {"ws": ws_id, "user_id": user_id, "token": _secrets.token_urlsafe(24), "now": now})
    if invites:
        db.commit()


def _accept_pending_invites_bg(user_id: str) -> None:
    """Background task wrapper — opens its own DB session so it doesn't block list_projects."""
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        _accept_pending_invites(user_id, db)
    except Exception:
        db.rollback()
    finally:
        db.close()


def _seed_starter_policies(db, workspace_id: uuid.UUID, now) -> None:
    from app.modules.guard.models import GuardPolicy
    policies = [
        # Destructive Operations
        {"rule_id": "no-rm-rf",                "description": "Block recursive deletes",                         "action": "BLOCK", "match_pattern": r"rm\s+-rf"},
        {"rule_id": "no-git-reset-hard",        "description": "Block hard resets",                              "action": "BLOCK", "match_pattern": r"git\s+reset\s+--hard"},
        {"rule_id": "no-force-push",            "description": "Block force pushes",                             "action": "BLOCK", "match_pattern": r"git\s+push\s+(--force|-f)\b"},
        {"rule_id": "no-drop-table",            "description": "Block DROP TABLE statements",                    "action": "BLOCK", "match_pattern": r"DROP\s+TABLE"},
        {"rule_id": "no-truncate-table",        "description": "Block TRUNCATE TABLE statements",               "action": "BLOCK", "match_pattern": r"TRUNCATE\s+TABLE"},
        {"rule_id": "no-delete-without-where",  "description": "Block DELETE statements without a WHERE clause", "action": "BLOCK", "match_pattern": r"DELETE\s+FROM\s+\w+\s*;"},
        # Secrets & Credentials
        {"rule_id": "no-env-commits",           "description": "Block committing .env files",                   "action": "BLOCK", "match_pattern": r"git (add|commit).+\.env"},
        {"rule_id": "no-hardcoded-secrets",     "description": "Warn on possible hardcoded secrets",            "action": "WARN",  "match_pattern": r"(API_KEY|SECRET|PASSWORD|TOKEN)\s*=\s*['\"][A-Za-z0-9+/]{16,}"},
        {"rule_id": "no-aws-keys",              "description": "Warn on hardcoded AWS access keys",             "action": "WARN",  "match_pattern": r"AKIA[0-9A-Z]{16}"},
        {"rule_id": "no-private-key-files",     "description": "Block writing private key files",               "action": "BLOCK", "match_pattern": r"-----BEGIN (RSA |EC )?PRIVATE KEY-----"},
        # Production Gates
        {"rule_id": "approve-prod-deploy",          "description": "Require approval for production deploys",           "action": "APPROVAL", "match_pattern": r"deploy.*(prod|production)|vercel.*--prod|railway.*prod"},
        {"rule_id": "approve-db-migration-prod",    "description": "Require approval for production DB migrations",     "action": "APPROVAL", "match_pattern": r"alembic upgrade|prisma migrate deploy"},
        {"rule_id": "approve-terraform-destroy",    "description": "Require approval for terraform destroy",            "action": "APPROVAL", "match_pattern": r"terraform\s+destroy"},
        {"rule_id": "approve-kubectl-delete",       "description": "Require approval for kubectl delete",               "action": "APPROVAL", "match_pattern": r"kubectl\s+delete"},
        {"rule_id": "approve-prod-env-edit",        "description": "Require approval when editing production env files", "action": "APPROVAL", "match_pattern": r"\.env\.prod(uction)?"},
        # Audit
        {"rule_id": "audit-migrations",   "description": "Audit migration file modifications", "action": "AUDIT", "match_pattern": r"alembic/versions/.*\.py|migrations/.*\.sql"},
        {"rule_id": "audit-ci-config",    "description": "Audit CI config modifications",       "action": "AUDIT", "match_pattern": r"\.(github|gitlab)/workflows/.*\.ya?ml|\.circleci/"},
        {"rule_id": "audit-dockerfile",   "description": "Audit Dockerfile modifications",      "action": "AUDIT", "match_pattern": r"Dockerfile"},
    ]
    for p in policies:
        db.add(GuardPolicy(
            workspace_id=workspace_id,
            rule_id=p["rule_id"],
            description=p["description"],
            action=p["action"],
            match_pattern=p["match_pattern"],
            enabled=True,
            builtin=True,
            created_at=now,
            updated_at=now,
        ))


@router.get("", response_model=list[ProjectOut])
def list_projects(
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
):
    # Accept pending invites synchronously so the workspace appears in this response
    _accept_pending_invites(user_id, db)

    # Query via workspace_users (new) with legacy owner_id fallback (UNION)
    rows = db.execute(text("""
        SELECT DISTINCT w.id, w.name, w.owner_id, w.is_approved, w.created_at,
               COUNT(wf.id) AS workflow_count
        FROM workspaces w
        LEFT JOIN workflows wf ON wf.workspace_id = w.id
        WHERE w.id IN (
            SELECT workspace_id FROM workspace_users WHERE clerk_user_id = :uid
            UNION
            SELECT id FROM workspaces WHERE owner_id = :uid
        )
        GROUP BY w.id
        ORDER BY w.created_at DESC
    """), {"uid": user_id}).fetchall()

    # Auto-register new users — create a default workspace + membership
    if not rows:
        project_id = uuid.uuid4()
        invite_code = uuid.uuid4().hex[:16]
        now = datetime.now(timezone.utc)
        import secrets as _secrets

        # 1. Create "Engineering" workspace
        db.execute(text("""
            INSERT INTO workspaces (id, name, owner_id, plan, is_approved, created_at, updated_at)
            VALUES (:id, 'Engineering', :owner_id, 'free', true, :now, :now)
        """), {"id": str(project_id), "owner_id": user_id, "now": now})

        # 2. Add owner as admin member
        db.execute(text("""
            INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at)
            VALUES (:ws, :uid, 'admin', :now)
            ON CONFLICT DO NOTHING
        """), {"ws": str(project_id), "uid": user_id, "now": now})

        # 3. Install Guard — create guard_config row
        db.execute(text("""
            INSERT INTO guard_config (workspace_id, invite_code, created_at)
            VALUES (:ws, :invite_code, :now)
            ON CONFLICT (workspace_id) DO NOTHING
        """), {"ws": str(project_id), "invite_code": invite_code, "now": now})

        # 4. Seed starter policies
        _seed_starter_policies(db, project_id, now)

        # 5. Add creator to guard_member_config
        db.execute(text("""
            INSERT INTO guard_member_config (workspace_id, clerk_user_id, member_token, active, joined_at)
            VALUES (:ws, :uid, :token, true, :now)
            ON CONFLICT (workspace_id, clerk_user_id) DO NOTHING
        """), {"ws": str(project_id), "uid": user_id, "token": _secrets.token_urlsafe(24), "now": now})

        db.commit()
        return [ProjectOut(id=str(project_id), name="Engineering", owner_id=user_id,
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

    project_id, now = uuid.uuid4(), datetime.now(timezone.utc)
    db.execute(text("""
        INSERT INTO workspaces (id, name, owner_id, plan, is_approved, created_at, updated_at)
        VALUES (:id, :name, :owner_id, 'free', true, :now, :now)
    """), {"id": str(project_id), "name": body.name.strip(), "owner_id": user_id, "now": now})

    # Creator is always admin of the new workspace
    db.execute(text("""
        INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at)
        VALUES (:ws, :uid, 'admin', :now)
        ON CONFLICT DO NOTHING
    """), {"ws": str(project_id), "uid": user_id, "now": now})

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


@router.patch("/{project_id}", response_model=ProjectOut)
def rename_project(
    project_id: str,
    body: dict,
    db: Session = Depends(get_db),
    user_id: Annotated[str, Depends(get_user_id)] = None,
    _: str = Depends(require_permission("platform.workspace.edit")),
):
    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Name cannot be empty")
    # Verify the authenticated user is actually a member of the target workspace (project_id).
    # This prevents a user from setting x-workspace-id to another workspace's ID.
    row = db.execute(text("SELECT id, owner_id FROM workspaces WHERE id = :id"), {"id": project_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    membership = db.execute(
        text("SELECT role FROM workspace_users WHERE workspace_id = :pid AND clerk_user_id = :uid"),
        {"pid": project_id, "uid": user_id},
    ).fetchone()
    if not membership and row.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Project not found")
    db.execute(text("UPDATE workspaces SET name = :name WHERE id = :id"), {"name": name, "id": project_id})
    db.commit()
    row = db.execute(text("""
        SELECT w.id, w.name, w.owner_id, w.is_approved, w.created_at,
               COUNT(wf.id) AS workflow_count
        FROM workspaces w
        LEFT JOIN workflows wf ON wf.workspace_id = w.id
        WHERE w.id = :id GROUP BY w.id
    """), {"id": project_id}).fetchone()
    return ProjectOut(id=str(row.id), name=row.name, owner_id=row.owner_id,
                      is_approved=row.is_approved, created_at=row.created_at,
                      workflow_count=row.workflow_count or 0)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    user_id: Annotated[str, Depends(get_user_id)] = None,
    _: str = Depends(require_permission("platform.workspace.edit")),
    purge: bool = False,  # ?purge=true — also deletes analytics, audit log, API keys, environments
):
    # Verify the authenticated user is actually a member of the target workspace (project_id).
    # This prevents a user from setting x-workspace-id to another workspace's ID.
    row = db.execute(text("SELECT id, owner_id FROM workspaces WHERE id = :id"), {"id": project_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    membership = db.execute(
        text("SELECT role FROM workspace_users WHERE workspace_id = :pid AND clerk_user_id = :uid"),
        {"pid": project_id, "uid": user_id},
    ).fetchone()
    if not membership and row.owner_id != user_id:
        raise HTTPException(status_code=403, detail="Project not found")

    # Deregister any GitHub webhooks before cascade-deleting workflows
    hooked = db.execute(text(
        "SELECT github_hook_id, github_hook_repo, environment_id FROM workflows "
        "WHERE workspace_id = :pid AND github_hook_id IS NOT NULL AND github_hook_repo IS NOT NULL"
    ), {"pid": project_id}).fetchall()
    if hooked:
        try:
            from app.routers.workflows import _deregister_git_webhook
            from app.routers.credentials import _git_token
            for row in hooked:
                try:
                    env_id = str(row.environment_id) if row.environment_id else None
                    token, provider = _git_token(project_id, db, env_id)
                    _deregister_git_webhook(token, row.github_hook_repo, row.github_hook_id, provider=provider)
                except Exception as e:
                    import logging as _logging
                    _logging.getLogger(__name__).warning("Webhook deregister skipped for %s: %s", row.github_hook_repo, e)
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).warning("Webhook deregistration pass failed: %s", e)

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

    if purge:
        # Permanently erase all remaining data — analytics, audit trail, API keys, environments
        db.execute(text("DELETE FROM run_analytics_events WHERE workspace_id = :pid"), {"pid": project_id})
        db.execute(text("DELETE FROM audit_log WHERE workspace_id = :pid"), {"pid": project_id})
        db.execute(text("DELETE FROM conduct_api_keys WHERE workspace_id = :pid"), {"pid": project_id})
        db.execute(text("DELETE FROM environments WHERE workspace_id = :pid"), {"pid": project_id})

    db.execute(text("DELETE FROM workspaces WHERE id = :pid"), {"pid": project_id})
    db.commit()


# ---------------------------------------------------------------------------
# Direct project lookup (no workspace cookie required — workspace derived from row)
# ---------------------------------------------------------------------------

@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: str,
    user_id: Annotated[str, Depends(get_user_id)],
    db: Session = Depends(get_db),
):
    row = db.execute(text("""
        SELECT p.id, p.workspace_id, p.name, p.slug, p.created_at, COUNT(w.id) AS agent_count
        FROM projects p
        LEFT JOIN workflows w ON w.project_id = p.id
        WHERE p.id = :pid
        GROUP BY p.id
    """), {"pid": project_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")

    proj_ws = str(row.workspace_id)
    member = db.execute(
        text("SELECT 1 FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid"),
        {"ws": proj_ws, "uid": user_id},
    ).fetchone()
    if not member and user_id != "dev":
        raise HTTPException(status_code=403, detail="Not a member of this workspace")

    return ProjectOut(id=str(row.id), workspace_id=proj_ws, name=row.name,
                      slug=row.slug or "", created_at=row.created_at, agent_count=row.agent_count or 0)


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
    out = []
    for r in rows:
        info = get_clerk_user_info(r.clerk_user_id)
        out.append(MemberOut(
            clerk_user_id=r.clerk_user_id, role=r.role,
            invited_by=r.invited_by, joined_at=r.joined_at,
            email=info["email"], name=info["name"],
        ))
    return out


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

        # Resolve workspace name for the notification
        ws_row = db.execute(text("SELECT name FROM workspaces WHERE id = :id"), {"id": workspace_id}).fetchone()
        workspace_name = ws_row.name if ws_row else "your workspace"

        # Guard is available by default for workspace members — sync is the only setup step needed
        guard_row = db.execute(
            text("SELECT id FROM guard_config WHERE workspace_id::text = :ws LIMIT 1"),
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
        RETURNING id, invited_email, role
    """), {"id": invite_id, "ws": workspace_id})
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Invite not found or already accepted")
    _audit(db, workspace_id=workspace_id, actor_id=user_id,
           actor_email=None, actor_role=actor_role,
           action="invite.cancelled", resource_type="invite",
           resource_id=invite_id, meta={"invited_email": row.invited_email, "role": row.role})
    db.commit()


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
    if not settings.admin_secret or not hmac.compare_digest(x_admin_secret or "", settings.admin_secret):
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
