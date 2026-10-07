"""Projects (workspaces) CRUD, templates, schemas and shared helpers (split from projects.py).

Owns the shared ``/projects`` APIRouter. Route registration order is part of
the public contract, so the endpoint modules form an import chain:
projects_core -> projects_members -> projects. Each module imports ``router``
from its predecessor.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Annotated
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.auth import get_user_id, require_permission, get_clerk_user_email
from app.core.config import settings
from app.core.database import get_db
from app.core.workspace_context import set_workspace_rls
from app.models.audit_log import AuditLog

log = structlog.get_logger("app.routers.projects")


router = APIRouter(prefix="/projects", tags=["projects"])


def _audit(db, *, workspace_id: str, actor_id: str, actor_email: str | None,
           actor_role: str | None, action: str, resource_type: str,
           resource_id: str | None = None, meta: dict | None = None) -> None:
    set_workspace_rls(db, workspace_id)
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


def _clerk_headers() -> dict:
    return {"Authorization": f"Bearer {settings.clerk_secret_key}", "Content-Type": "application/json"}


def _send_clerk_invite(db, workspace_id: str, email: str, conduct_role: str, invite_id: str) -> None:
    """Send a Clerk org invitation and store clerk_invitation_id back on workspace_invites."""
    import httpx as _httpx
    if not settings.clerk_secret_key:
        return  # local dev without Clerk — skip silently

    # Ensure workspace has a clerk_org_id; create one if missing
    ws = db.execute(
        text("SELECT clerk_org_id, owner_id, name FROM workspaces WHERE id = :id"),
        {"id": workspace_id},
    ).fetchone()
    if not ws:
        return
    org_id = ws.clerk_org_id
    if not org_id:
        try:
            r = _httpx.post(
                "https://api.clerk.com/v1/organizations",
                headers=_clerk_headers(),
                json={"name": ws.name or f"workspace-{workspace_id[:8]}", "created_by": ws.owner_id},
                timeout=10,
            )
            r.raise_for_status()
            org_id = r.json()["id"]
            db.execute(
                text("UPDATE workspaces SET clerk_org_id = :oid WHERE id = :id"),
                {"oid": org_id, "id": workspace_id},
            )
            db.commit()
        except Exception as e:
            log.warning("clerk.org_create_failed", workspace_id=workspace_id, error=str(e))
            return

    # Map Conduct role → Clerk role
    clerk_role = "org:admin" if conduct_role == "admin" else "org:member"

    try:
        r = _httpx.post(
            f"https://api.clerk.com/v1/organizations/{org_id}/invitations",
            headers=_clerk_headers(),
            json={"email_address": email, "role": clerk_role},
            timeout=10,
        )
        if r.status_code == 422:
            # Already a member or invite exists — not a fatal error
            log.info("clerk.invite_skipped", email=email, detail=r.text)
            return
        r.raise_for_status()
        clerk_inv_id = r.json().get("id")
        if clerk_inv_id:
            db.execute(
                text("UPDATE workspace_invites SET clerk_invitation_id = :cid WHERE id = :id"),
                {"cid": clerk_inv_id, "id": invite_id},
            )
            db.commit()
    except Exception as e:
        log.warning("clerk.invite_failed", email=email, error=str(e))


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


class ProjectDetailOut(BaseModel):
    """Response for GET /projects/{id} — actual projects table (not workspaces).
    Distinct from ProjectOut which is used by /workspaces/* endpoints.
    """
    id: str
    workspace_id: str
    name: str
    slug: str
    created_at: datetime
    agent_count: int = 0


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
    if settings.auth_mode == "proxy":
        return
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
    """Install the conduct-base skill pack for a new workspace.

    Replaces the legacy per-rule write into guard_policies. The base pack
    JSONB carries the same set of starter rules (destructive ops, secrets,
    production gates, audit) plus the new findings vocabulary fields."""
    from app.modules.guard.models import WorkspaceSkillPack
    existing = db.get(WorkspaceSkillPack, (workspace_id, "conduct-base"))
    if existing:
        return
    db.add(WorkspaceSkillPack(
        workspace_id=workspace_id,
        pack_slug="conduct-base",
        installed_by="system:workspace_create",
        installed_at=now,
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
        # Don't auto-create if the user was just added via invite resolution
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

    # Never auto-create a workspace for an invited user — they belong to an existing one
    email_for_invite_check = get_clerk_user_email(user_id)
    has_pending_or_accepted_invite = email_for_invite_check and db.execute(text("""
        SELECT 1 FROM workspace_invites WHERE invited_email = :email LIMIT 1
    """), {"email": email_for_invite_check}).fetchone()

    if not rows and settings.auth_mode == "proxy":
        return []

    if not rows and not has_pending_or_accepted_invite:
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
        member_token = _secrets.token_urlsafe(24)
        db.execute(text("""
            INSERT INTO guard_member_config (workspace_id, clerk_user_id, member_token, active, joined_at)
            VALUES (:ws, :uid, :token, true, :now)
            ON CONFLICT (workspace_id, clerk_user_id) DO NOTHING
        """), {"ws": str(project_id), "uid": user_id, "token": member_token, "now": now})

        # ponytail: CONDUCT_PROXY_URL removed from workspace_config — always served from settings.conduct_proxy_url

        # 7. Pre-seed Conduct AI Guard MCP server
        # Token goes in encrypted_auth (rendered as Authorization: Bearer header
        # by the MCP client at call time — see runtime/integrations/mcp_client.py),
        # not in URL (#800 — avoids leaking in access logs).
        from app.core.crypto import encrypt as _enc_token
        _enc_bearer = _enc_token({"token": member_token})
        db.execute(text("""
            INSERT INTO mcp_servers (id, workspace_id, environment_id, name, url, transport, encrypted_auth, created_at)
            VALUES (gen_random_uuid(), :ws, NULL, 'Conduct AI Guard',
                    'https://gateway.conductai.ai/mcp',
                    'http', :auth, :now)
            ON CONFLICT DO NOTHING
        """), {"ws": str(project_id), "auth": _enc_bearer, "now": now})

        # Pre-seed well-known public MCP servers (no auth — user adds token via Integrations)
        _PUBLIC_MCP = [
            ("slack",  "https://mcp.slack.com",      "sse"),
            ("linear", "https://mcp.linear.app/mcp", "http"),
        ]
        for _name, _url, _transport in _PUBLIC_MCP:
            db.execute(text("""
                INSERT INTO mcp_servers
                    (id, workspace_id, environment_id, name, url, transport, is_system, encrypted_auth, created_at)
                VALUES
                    (gen_random_uuid(), :ws, NULL, :name, :url, :transport, true, NULL, :now)
                ON CONFLICT DO NOTHING
            """), {"ws": str(project_id), "name": _name, "url": _url, "transport": _transport, "now": now})

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
    if not user_id:
        raise HTTPException(status_code=401, detail="This endpoint requires a Clerk user session")
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
    if not user_id:
        raise HTTPException(status_code=401, detail="This endpoint requires a Clerk user session")
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
        db.execute(text("DELETE FROM environments WHERE workspace_id = :pid"), {"pid": project_id})

    db.execute(text("DELETE FROM workspaces WHERE id = :pid"), {"pid": project_id})
    db.commit()


# ---------------------------------------------------------------------------
# Direct project lookup (no workspace cookie required — workspace derived from row)
# ---------------------------------------------------------------------------

@router.get("/{project_id}", response_model=ProjectDetailOut)
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

    return ProjectDetailOut(id=str(row.id), workspace_id=proj_ws, name=row.name,
                            slug=row.slug or "", created_at=row.created_at, agent_count=row.agent_count or 0)


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
