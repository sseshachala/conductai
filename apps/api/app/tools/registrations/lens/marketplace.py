"""Lens tool registrations — marketplace domain.

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

# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="list_installed_packs",
        description="List installed skill packs for this workspace's org.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("list_installed_packs"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="browse_marketplace",
        description="Available skill packs in the catalog (latest version per slug). Optional query for substring match on slug/name/description.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Substring search"},
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("browse_marketplace"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_pack_details",
        description="One skill pack's latest version with the full rule list.",
        input_schema={
            "type": "object",
            "properties": {"slug": {"type": "string", "description": "Pack slug"}},
            "required": ["slug"],
        },
        impl=_impl("get_pack_details"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
