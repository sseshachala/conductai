"""Lens tool registrations — discovery domain.

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
def list_discovered_agents(ctx, framework: str | None = None, since: str | None = None):
    """Discovered AI agents in the workspace — name, framework, source,
    risk_score, under_guard, proxy_routed. Optional framework filter (e.g.
    'langchain', 'crewai') and since ISO-8601 lower bound on last_seen_at.
    """
    import uuid as _uuid
    from datetime import datetime
    from app.core.database import SessionLocal
    from app.modules.guard.models import DiscoveredAgent
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        q = db.query(DiscoveredAgent).filter(DiscoveredAgent.workspace_id == ws_uuid)
        if framework:
            q = q.filter(DiscoveredAgent.framework == framework)
        if since:
            try:
                q = q.filter(DiscoveredAgent.last_seen_at >= datetime.fromisoformat(since))
            except ValueError:
                pass
        rows = q.order_by(DiscoveredAgent.last_seen_at.desc()).all()
        return {
            "count": len(rows),
            "agents": [
                {
                    "name": r.name,
                    "framework": r.framework,
                    "source": r.source,
                    "location": r.location,
                    "risk_score": r.risk_score,
                    "under_guard": r.under_guard,
                    "proxy_routed": r.proxy_routed,
                    "first_seen_at": r.first_seen_at.isoformat() if r.first_seen_at else None,
                    "last_seen_at": r.last_seen_at.isoformat() if r.last_seen_at else None,
                }
                for r in rows
            ],
        }
    finally:
        db.close()


# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_discovery_summary",
        description="Discovered agents inventory — total, coverage, high-risk agents, per-framework breakdown.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_discovery_summary"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_discovered_agents",
        description="AI agents discovered in this workspace by the discovery daemon. Optional framework filter (langchain/crewai/…) and since lower bound.",
        input_schema={
            "type": "object",
            "properties": {
                "framework": {"type": "string"},
                "since": {"type": "string", "description": "ISO-8601 lower bound on last_seen_at"},
            },
            "required": [],
        },
        impl=list_discovered_agents,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
