"""Lens tool registrations — ops domain.

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
def get_autopilot_activity(ctx, since: str | None = None, limit: int = 50, status: str | None = None):
    """Feed of autopilot-driven security activity. Synthesized from
    SecurityFinding rows scoped to this workspace, ordered by updated_at
    desc. Optional since (ISO-8601 lower bound on updated_at), status
    (open/triaging/fixed/dismissed), limit (default 50, max 500).
    """
    import uuid as _uuid
    from datetime import datetime
    from app.core.database import SessionLocal
    from app.models.security_finding import SecurityFinding
    limit = min(max(int(limit or 50), 1), 500)
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        q = db.query(SecurityFinding).filter(SecurityFinding.workspace_id == ws_uuid)
        if status:
            q = q.filter(SecurityFinding.status == status)
        if since:
            try:
                q = q.filter(SecurityFinding.updated_at >= datetime.fromisoformat(since))
            except ValueError:
                pass
        rows = q.order_by(SecurityFinding.updated_at.desc()).limit(limit).all()
        return {
            "count": len(rows),
            "findings": [
                {
                    "id": str(r.id),
                    "tool": r.tool,
                    "severity": r.severity,
                    "type": r.type,
                    "file": r.file,
                    "line": r.line,
                    "description": r.description,
                    "status": r.status,
                    "repo_full_name": r.repo_full_name,
                    "run_id": r.run_id,
                    "github_issue_url": r.github_issue_url,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "updated_at": r.updated_at.isoformat() if r.updated_at else None,
                }
                for r in rows
            ],
        }
    finally:
        db.close()


# ── Migrated from Executor (epic #1655 PR 6/9) ─────────────────────────
def list_pending_approvals(ctx, status: str = "pending", limit: int = 20, since: str | None = None):
    """List HITL approval requests."""
    import uuid as _uuid
    from datetime import datetime, timezone
    from app.core.database import SessionLocal
    from app.modules.guard.models import GuardApprovalRequest
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        q = db.query(GuardApprovalRequest).filter(GuardApprovalRequest.workspace_id == ws_uuid)
        status = (status or "pending").lower()
        if status != "all":
            q = q.filter(GuardApprovalRequest.status == status)
        if since:
            s = since.strip().lower()
            cutoff = None
            if s == "today":
                cutoff = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                try:
                    cutoff = datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except ValueError:
                    cutoff = None
            if cutoff:
                q = q.filter(GuardApprovalRequest.created_at >= cutoff)
        rows = q.order_by(GuardApprovalRequest.created_at.desc()).limit(min(limit, 100)).all()
        return [
            {"id": str(r.id), "status": r.status, "rule_id": r.rule_id, "tool_name": r.tool_name,
             "requester_email": r.requester_email, "decided_by_email": r.decided_by_email,
             "decided_at": r.decided_at.isoformat() if r.decided_at else None,
             "created_at": r.created_at.isoformat() if r.created_at else None,
             "timeout_at": r.timeout_at.isoformat() if r.timeout_at else None}
            for r in rows
        ]
    finally:
        db.close()


def get_approval(ctx, id: str):
    """One approval request by id."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.modules.guard.models import GuardApprovalRequest
    try:
        rid = _uuid.UUID(id)
    except ValueError:
        return {"error": "id must be a UUID"}
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        r = db.query(GuardApprovalRequest).filter(
            GuardApprovalRequest.id == rid, GuardApprovalRequest.workspace_id == ws_uuid
        ).first()
        if not r:
            return {"error": "Approval not found"}
        return {"id": str(r.id), "status": r.status, "rule_id": r.rule_id, "tool_name": r.tool_name,
                "tool_input": r.tool_input, "requester_email": r.requester_email,
                "decided_by_email": r.decided_by_email,
                "decided_at": r.decided_at.isoformat() if r.decided_at else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "timeout_at": r.timeout_at.isoformat() if r.timeout_at else None}
    finally:
        db.close()


def get_audit_events(ctx, actor_email: str | None = None, action: str | None = None,
                     resource_type: str | None = None, since: str | None = None,
                     until: str | None = None, limit: int = 25):
    """Platform audit log with filters."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.audit_log import AuditLog
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        q = db.query(AuditLog).filter(AuditLog.workspace_id == ws_uuid)
        if actor_email:   q = q.filter(AuditLog.actor_email == actor_email)
        if action:        q = q.filter(AuditLog.action == action)
        if resource_type: q = q.filter(AuditLog.resource_type == resource_type)
        if since:         q = q.filter(AuditLog.created_at >= since)
        if until:         q = q.filter(AuditLog.created_at <= until)
        rows = q.order_by(AuditLog.created_at.desc()).limit(min(limit, 100)).all()
        return [{"id": str(r.id), "actor_email": r.actor_email, "actor_role": r.actor_role,
                 "action": r.action, "resource_type": r.resource_type,
                 "resource_id": r.resource_id, "metadata": r.meta,
                 "created_at": r.created_at.isoformat() if r.created_at else None}
                for r in rows]
    finally:
        db.close()


def search_audit_log(ctx, q: str, limit: int = 25):
    """Substring search across audit log."""
    import uuid as _uuid
    from sqlalchemy import func as sa_func, or_ as sa_or
    from app.core.database import SessionLocal
    from app.models.audit_log import AuditLog
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        like = f"%{q.lower()}%"
        rows = (db.query(AuditLog)
                .filter(AuditLog.workspace_id == ws_uuid,
                        sa_or(sa_func.lower(AuditLog.action).like(like),
                              sa_func.lower(AuditLog.actor_email).like(like),
                              sa_func.lower(AuditLog.resource_type).like(like),
                              sa_func.lower(AuditLog.resource_id).like(like)))
                .order_by(AuditLog.created_at.desc()).limit(min(limit, 100)).all())
        return [{"id": str(r.id), "actor_email": r.actor_email, "action": r.action,
                 "resource_type": r.resource_type, "resource_id": r.resource_id,
                 "created_at": r.created_at.isoformat() if r.created_at else None}
                for r in rows]
    finally:
        db.close()


def list_alerts(ctx, severity: str | None = None, event_type: str | None = None,
                include_resolved: bool = False, since: str | None = None, limit: int = 25):
    """Watchdog alerts. Optional filters."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.watchdog_event import WatchdogEvent
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        q = db.query(WatchdogEvent).filter(WatchdogEvent.workspace_id == ws_uuid)
        if severity:
            q = q.filter(WatchdogEvent.severity == severity.lower())
        if event_type:
            q = q.filter(WatchdogEvent.event_type == event_type)
        if not include_resolved:
            q = q.filter(WatchdogEvent.resolved_at.is_(None))
        if since:
            q = q.filter(WatchdogEvent.created_at >= since)
        rows = q.order_by(WatchdogEvent.created_at.desc()).limit(min(limit, 100)).all()
        return [{"id": str(r.id), "event_type": r.event_type, "severity": r.severity,
                 "run_id": str(r.run_id) if r.run_id else None,
                 "workflow_id": str(r.workflow_id) if r.workflow_id else None,
                 "payload": r.payload,
                 "created_at": r.created_at.isoformat() if r.created_at else None,
                 "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None}
                for r in rows]
    finally:
        db.close()


def get_alert(ctx, id: str):
    """One alert by id."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.watchdog_event import WatchdogEvent
    try:
        aid = _uuid.UUID(id)
    except ValueError:
        return {"error": "id must be a UUID"}
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        r = db.query(WatchdogEvent).filter(
            WatchdogEvent.id == aid, WatchdogEvent.workspace_id == ws_uuid).first()
        if not r:
            return {"error": "Alert not found"}
        return {"id": str(r.id), "event_type": r.event_type, "severity": r.severity,
                "run_id": str(r.run_id) if r.run_id else None,
                "workflow_id": str(r.workflow_id) if r.workflow_id else None,
                "payload": r.payload,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "resolved_at": r.resolved_at.isoformat() if r.resolved_at else None}
    finally:
        db.close()


# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="list_pending_approvals",
        description="HITL approval queue. status = pending (default) | approved | rejected | timed_out | all.",
        input_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["pending", "approved", "rejected", "timed_out", "all"]},
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=list_pending_approvals,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_approval",
        description="One approval request with full tool_input payload.",
        input_schema={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Approval UUID"}},
            "required": ["id"],
        },
        impl=get_approval,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_audit_events",
        description=(
            "Platform audit events (invites, role changes, credential edits, run triggers). "
            "Separate from Guard events — this is org-wide platform activity."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "actor_email": {"type": "string"},
                "action": {"type": "string", "description": "e.g. run.triggered, invite.sent"},
                "resource_type": {"type": "string"},
                "since": _TS_SINCE, "until": _TS_UNTIL,
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=get_audit_events,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="search_audit_log",
        description="Substring search across audit action, actor_email, resource_type, resource_id.",
        input_schema={
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Search query"},
                "limit": _LIMIT,
            },
            "required": ["q"],
        },
        impl=search_audit_log,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_alerts",
        description=(
            "Watchdog alerts (stale worker, credential expiry, silent playbook, "
            "repeated failures). Excludes resolved unless include_resolved=true."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "severity": {"type": "string", "enum": ["info", "warning", "error"]},
                "event_type": {"type": "string"},
                "include_resolved": {"type": "boolean"},
                "since": _TS_SINCE,
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=list_alerts,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_alert",
        description="One watchdog alert with full payload.",
        input_schema={
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Alert UUID"}},
            "required": ["id"],
        },
        impl=get_alert,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_autopilot_activity",
        description="Autopilot feed — recent SecurityFinding rows (open/triaging/fixed/dismissed). Optional since (ISO-8601) + status filter + limit (default 50, max 500).",
        input_schema={
            "type": "object",
            "properties": {
                "since": {"type": "string", "description": "ISO-8601 lower bound on updated_at"},
                "status": {"type": "string", "description": "Filter: open/triaging/fixed/dismissed"},
                "limit": {"type": "integer", "minimum": 1},
            },
            "required": [],
        },
        impl=get_autopilot_activity,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
