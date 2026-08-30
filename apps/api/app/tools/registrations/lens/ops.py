"""Lens tool registrations — ops domain.

Split from the flat lens.py on 2026-08-29 to keep each file focused on
one KPI/read/action domain. See lens/_shared.py for common constants and
helpers; see lens/__init__.py for the composition root.

Do not import from other domain files — depend only on _shared.
"""
from __future__ import annotations

from app.tools.types import ToolDef
from app.tools.registrations.lens._shared import (
    _impl,
    _run,
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
        impl=_impl("list_pending_approvals"),
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
        impl=_impl("get_approval"),
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
        impl=_impl("get_audit_events"),
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
        impl=_impl("search_audit_log"),
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
        impl=_impl("list_alerts"),
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
        impl=_impl("get_alert"),
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
