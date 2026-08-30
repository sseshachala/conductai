"""Lens tool registrations — guard_core domain.

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
        name="get_spend_summary",
        description="Guard workspace spend summary — events today, cost, active devs, tokens saved. Optional month filter (YYYY-MM).",
        input_schema={"type": "object", "properties": {"month": {"type": "string"}}, "required": []},
        impl=_impl("get_spend_summary"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_recent_events",
        description="Recent Guard audit events, optionally filtered by decision, rule_id, time range.",
        input_schema={
            "type": "object",
            "properties": {
                "limit": _LIMIT, "decision": _DECISION,
                "since": _TS_SINCE, "until": _TS_UNTIL, "rule_id": _RULE_ID,
            },
            "required": [],
        },
        impl=_impl("get_recent_events"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_sessions",
        description="Recent Guard sessions (agent transcripts) for the workspace.",
        input_schema={"type": "object", "properties": {"limit": _LIMIT}, "required": []},
        impl=_impl("get_sessions"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_event_count",
        description="Exact COUNT of audit events matching filters. Use for 'how many X' questions.",
        input_schema={
            "type": "object",
            "properties": {
                "decision": _DECISION, "since": _TS_SINCE,
                "until": _TS_UNTIL, "rule_id": _RULE_ID,
            },
            "required": [],
        },
        impl=_impl("get_event_count"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="search_memory",
        description="Semantic search across team session memory (past agent work summaries).",
        input_schema={
            "type": "object",
            "properties": {"q": {"type": "string"}, "limit": _LIMIT},
            "required": ["q"],
        },
        impl=_impl("search_memory"),
        annotations=_READ_ONLY_OPEN_WORLD,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="search_sessions",
        description="Semantic search across session reports (Guard-generated agent transcripts).",
        input_schema={
            "type": "object",
            "properties": {"q": {"type": "string"}, "limit": _LIMIT},
            "required": ["q"],
        },
        impl=_impl("search_sessions"),
        annotations=_READ_ONLY_OPEN_WORLD,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_team_memory_feed",
        description="Recent team memory entries. No embeddings required.",
        input_schema={"type": "object", "properties": {"limit": _LIMIT}, "required": []},
        impl=_impl("get_team_memory_feed"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_session_reports_feed",
        description="Recent session reports. No embeddings required.",
        input_schema={"type": "object", "properties": {"limit": _LIMIT}, "required": []},
        impl=_impl("get_session_reports_feed"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="search_knowledge",
        description="Semantic search across all Guard knowledge (audit events, rules, discovered agents). Optional kind filter.",
        input_schema={
            "type": "object",
            "properties": {
                "q": {"type": "string"},
                "kind": {"type": "string", "description": "Optional source_kind filter"},
                "limit": _LIMIT,
            },
            "required": ["q"],
        },
        impl=_impl("search_knowledge"),
        annotations=_READ_ONLY_OPEN_WORLD,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_guard_config",
        description="Workspace Guard config — enforcement mode, fail mode, persona, notification settings.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_guard_config"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_budgets",
        description="Workspace and per-developer spend budgets.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_budgets"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_correlated_events",
        description="Guard audit events grouped by session. Defaults to blocked events. Time-bounded via since/until.",
        input_schema={
            "type": "object",
            "properties": {
                "decision": _DECISION, "since": _TS_SINCE,
                "until": _TS_UNTIL, "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("get_correlated_events"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_savings_summary",
        description="Team token/cost savings from RTK + Booster.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_savings_summary"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
