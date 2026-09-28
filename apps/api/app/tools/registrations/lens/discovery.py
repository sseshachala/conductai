"""Lens tool registrations — discovery domain.

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
def get_discovery_summary(ctx):
    """Live installation evidence, scoped to the selected workspace."""
    from app.core.database import SessionLocal
    from app.modules.guard.discovery_inventory import workspace_inventory, summarize
    from fastapi.encoders import jsonable_encoder
    db = SessionLocal()
    try:
        agents = workspace_inventory(db, ctx.workspace_id)
        return jsonable_encoder({**summarize(agents), "agents": agents})
    finally:
        db.close()


def list_discovered_agents(ctx, framework: str | None = None, since: str | None = None):
    """Live findings; configuration does not prove enforcement."""
    from datetime import datetime, timezone
    from app.core.database import SessionLocal
    from app.modules.guard.discovery_inventory import workspace_inventory
    from fastapi.encoders import jsonable_encoder
    db = SessionLocal()
    try:
        agents = workspace_inventory(db, ctx.workspace_id)
    finally:
        db.close()
    if framework:
        agents = [a for a in agents if a["framework"] == framework]
    if since:
        lower = datetime.fromisoformat(since)
        if lower.tzinfo is None:
            lower = lower.replace(tzinfo=timezone.utc)
        agents = [a for a in agents if a["last_seen_at"] and
                  a["last_seen_at"].replace(tzinfo=a["last_seen_at"].tzinfo or timezone.utc) >= lower]
    return jsonable_encoder({"count": len(agents), "agents": agents})



# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_discovery_summary",
        description="Live discovery inventory: installed tools, possible integrations, freshness, configuration and observed hook evidence. Not a protection percentage.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_discovery_summary,
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
