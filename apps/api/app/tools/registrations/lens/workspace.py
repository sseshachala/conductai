"""Lens tool registrations — workspace domain.

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


# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="list_integrations",
        description="All integrations (Slack, GitHub, Okta, Vercel, ...) configured for this workspace.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("list_integrations"),
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
        impl=_impl("get_integration_status"),
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
        impl=_impl("list_members"),
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
        impl=_impl("get_member"),
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
        impl=_impl("list_projects"),
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
        impl=_impl("get_project"),
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
        impl=_impl("list_agent_identities"),
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
        impl=_impl("get_agent_identity_count"),
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
