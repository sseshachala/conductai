"""Lens tool registrations — workspace domain.

Split from the flat lens.py on 2026-08-29 to keep each file focused on
one KPI/read/action domain. See lens/_shared.py for common constants and
helpers; see lens/__init__.py for the composition root.

Do not import from other domain files — depend only on _shared.
"""
from __future__ import annotations

from app.tools.types import ToolDef
from app.tools.registrations.lens._shared import (
    _actor_impl,
    _window_start,
    _LIMIT,
    _DECISION,
    _TS_SINCE,
    _TS_UNTIL,
    _RULE_ID,
    _DAYS_WINDOW,
    _TIME_WINDOW,
    _READ_ONLY,
    _READ_ONLY_OPEN_WORLD,
    _LENS_TAGS,
    _ACTOR_TAGS
)


# ── Free-function tool implementations ─────────────────────────────────
def get_workspace_kpis(ctx, time_window: str = "last_24h"):
    """Rollup counters for the workspace over a time window.

    Returns: blocked_calls (Guard blocks in window), spend (proxy cost sum),
    runs {total/succeeded/failed} (workflow runs in window), active_agents
    (distinct agent identities in window).
    """
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.modules.guard.models import GuardAuditEvent
    from app.models.run import Run
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        since = _window_start(time_window)

        blocked_calls = (
            db.query(GuardAuditEvent)
            .filter(
                GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.decision == "block",
                GuardAuditEvent.ts >= since,
            )
            .count()
        )

        spend_rows = (
            db.query(GuardAuditEvent.cost_usd_after)
            .filter(
                GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.ts >= since,
                GuardAuditEvent.cost_usd_after.isnot(None),
            )
            .all()
        )
        spend_total = sum((r[0] or 0.0) for r in spend_rows)

        runs = (
            db.query(Run)
            .filter(Run.workspace_id == ws_uuid, Run.created_at >= since)
            .all()
        )
        run_status: dict[str, int] = {}
        for r in runs:
            run_status[r.status] = run_status.get(r.status, 0) + 1

        active_agents = (
            db.query(GuardAuditEvent.agent_identity_id)
            .filter(
                GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.ts >= since,
                GuardAuditEvent.agent_identity_id.isnot(None),
            )
            .distinct()
            .count()
        )

        return {
            "time_window": time_window,
            "since": since.isoformat(),
            "blocked_calls": blocked_calls,
            "spend": {"amount_usd": round(spend_total, 6), "currency": "USD"},
            "runs": {
                "total": sum(run_status.values()),
                "succeeded": run_status.get("succeeded", 0),
                "failed": run_status.get("failed", 0),
                "by_status": run_status,
            },
            "active_agents": active_agents,
        }
    finally:
        db.close()


# ── Migrated from Executor (epic #1655 PR 5/9) ─────────────────────────
def list_agent_identities(ctx, status: str = "active", limit: int = 20):
    """List agent identities in this workspace."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.modules.agent_identity.models import AgentIdentity
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        q = db.query(AgentIdentity).filter(AgentIdentity.workspace_id == ws_uuid)
        status = (status or "active").lower()
        if status != "all":
            q = q.filter(AgentIdentity.lifecycle_state == status)
        rows = q.order_by(AgentIdentity.created_at.desc()).limit(min(limit, 100)).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "token_prefix": r.token_prefix,
                "lifecycle_state": r.lifecycle_state,
                "risk_tier": r.risk_tier,
                "source": r.source,
                "platform_of_origin": r.platform_of_origin,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "deactivated_at": r.deactivated_at.isoformat() if r.deactivated_at else None,
                "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            }
            for r in rows
        ]
    finally:
        db.close()


def get_agent_identity_count(ctx, status: str = "active"):
    """Exact COUNT of agent identities matching lifecycle_state."""
    import uuid as _uuid
    from sqlalchemy import func as sa_func
    from app.core.database import SessionLocal
    from app.modules.agent_identity.models import AgentIdentity
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        q = db.query(sa_func.count(AgentIdentity.id)).filter(
            AgentIdentity.workspace_id == ws_uuid
        )
        status = (status or "active").lower()
        if status != "all":
            q = q.filter(AgentIdentity.lifecycle_state == status)
        return {"count": int(q.scalar() or 0), "status": status}
    finally:
        db.close()


def list_integrations(ctx):
    """All configured integrations for the workspace."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.integration import Integration
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        rows = db.query(Integration).filter(Integration.workspace_id == ws_uuid).all()
        return [{"id": str(r.id), "service": r.service, "auth_method": r.auth_method,
                 "handle": r.handle, "scopes": list(r.scopes) if r.scopes else [],
                 "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
                 "created_at": r.created_at.isoformat() if r.created_at else None}
                for r in rows]
    finally:
        db.close()


def get_integration_status(ctx, service: str):
    """Status + metadata for one integration by service slug."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.integration import Integration
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        r = db.query(Integration).filter(
            Integration.workspace_id == ws_uuid, Integration.service == service.lower()
        ).first()
        if not r:
            return {"service": service, "configured": False}
        return {"service": r.service, "configured": True, "auth_method": r.auth_method,
                "handle": r.handle, "scopes": list(r.scopes) if r.scopes else [],
                "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None}
    finally:
        db.close()


def list_members(ctx, role: str | None = None, limit: int = 50):
    """List workspace members. Optional role filter."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.workspace_user import WorkspaceUser
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        q = db.query(WorkspaceUser).filter(WorkspaceUser.workspace_id == ws_uuid)
        if role:
            q = q.filter(WorkspaceUser.role == role.lower())
        rows = q.order_by(WorkspaceUser.joined_at.desc()).limit(min(limit, 200)).all()
        return [{"clerk_user_id": r.clerk_user_id, "role": r.role, "invited_by": r.invited_by,
                 "joined_at": r.joined_at.isoformat() if r.joined_at else None}
                for r in rows]
    finally:
        db.close()


def get_member(ctx, clerk_user_id: str):
    """One member by clerk_user_id."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.workspace_user import WorkspaceUser
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        r = db.query(WorkspaceUser).filter(
            WorkspaceUser.workspace_id == ws_uuid, WorkspaceUser.clerk_user_id == clerk_user_id
        ).first()
        if not r:
            return {"error": "Member not found"}
        return {"clerk_user_id": r.clerk_user_id, "role": r.role,
                "role_id": str(r.role_id) if r.role_id else None,
                "invited_by": r.invited_by,
                "joined_at": r.joined_at.isoformat() if r.joined_at else None}
    finally:
        db.close()


def list_projects(ctx, limit: int = 50):
    """List projects in the workspace."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.project import Project
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        rows = (db.query(Project).filter(Project.workspace_id == ws_uuid)
                .order_by(Project.created_at.desc()).limit(min(limit, 200)).all())
        return [{"id": str(r.id), "name": r.name, "slug": r.slug,
                 "project_type": r.project_type,
                 "created_at": r.created_at.isoformat() if r.created_at else None}
                for r in rows]
    finally:
        db.close()


def get_project(ctx, id_or_slug: str):
    """One project by UUID or slug."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.project import Project
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        q = db.query(Project).filter(Project.workspace_id == ws_uuid)
        try:
            r = q.filter(Project.id == _uuid.UUID(id_or_slug)).first()
        except ValueError:
            r = q.filter(Project.slug == id_or_slug).first()
        if not r:
            return {"error": "Project not found"}
        return {"id": str(r.id), "name": r.name, "slug": r.slug,
                "project_type": r.project_type,
                "security_finding_id": r.security_finding_id,
                "created_at": r.created_at.isoformat() if r.created_at else None}
    finally:
        db.close()


# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="list_integrations",
        description="All integrations (Slack, GitHub, Okta, Vercel, ...) configured for this workspace.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=list_integrations,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_integration_status",
        description="One integration by service. Returns configured=false if none.",
        input_schema={
            "type": "object",
            "properties": {"service": {"type": "string", "description": "e.g. github, slack, okta, vercel"}},
            "required": ["service"],
        },
        impl=get_integration_status,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_members",
        description="Workspace members with role. Optional role filter (admin/developer/security/viewer).",
        input_schema={
            "type": "object",
            "properties": {
                "role": {"type": "string", "enum": ["admin", "developer", "security", "viewer"]},
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=list_members,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_member",
        description="One workspace member's role + join info by Clerk user id.",
        input_schema={
            "type": "object",
            "properties": {"clerk_user_id": {"type": "string"}},
            "required": ["clerk_user_id"],
        },
        impl=get_member,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_projects",
        description="Projects in this workspace.",
        input_schema={
            "type": "object",
            "properties": {"limit": _LIMIT},
            "required": [],
        },
        impl=list_projects,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_project",
        description="One project by UUID or slug.",
        input_schema={
            "type": "object",
            "properties": {"id_or_slug": {"type": "string"}},
            "required": ["id_or_slug"],
        },
        impl=get_project,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_agent_identities",
        description=(
            "List agent identities in this workspace. status = active (default) | "
            "deactivated | pending_review | expired | all. Returns id, name, "
            "token_prefix, lifecycle_state, risk_tier, source, created_at, "
            "deactivated_at, last_used_at, expires_at."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "deactivated", "pending_review", "expired", "all"],
                },
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=list_agent_identities,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_agent_identity_count",
        description=(
            "Exact COUNT of agent identities matching status. Use for 'how many "
            "invalidated/active/expired identities' questions."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "deactivated", "pending_review", "expired", "all"],
                },
            },
            "required": [],
        },
        impl=get_agent_identity_count,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_workspace_kpis",
        description="Workspace rollup — blocked calls, spend, workflow runs, active agents over a time window (last_24h / last_7d / mtd).",
        input_schema={
            "type": "object",
            "properties": {
                "time_window": {"type": "string", "description": "'last_24h' (default) / 'last_7d' / 'mtd'."},
            },
            "required": [],
        },
        impl=get_workspace_kpis,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
