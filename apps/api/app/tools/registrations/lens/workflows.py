"""Lens tool registrations — workflows domain.

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
def list_playbooks(ctx, category: str | None = None):
    """Playbook catalog — builtin templates + user-submitted templates.
    Optional category filter (e.g. 'incident_response', 'ci_cd')."""
    from app.core.database import SessionLocal
    from app.routers.playbooks import _TEMPLATE_PLAYBOOKS, _PLAYBOOK_META
    from app.models.workflow import Workflow

    entries: list[dict] = []
    for slug in _TEMPLATE_PLAYBOOKS:
        meta = _PLAYBOOK_META.get(slug)
        if not meta:
            continue
        if category and meta.get("category") != category:
            continue
        entries.append({
            "slug": slug,
            "name": slug.replace("_", " ").title(),
            "description": meta.get("description"),
            "category": meta.get("category", "Other"),
            "tags": meta.get("tags", []),
            "featured": meta.get("featured", False),
            "source": "builtin",
        })
    db = SessionLocal()
    try:
        db_playbooks = (
            db.query(Workflow)
            .filter(Workflow.workspace_id == ctx.workspace_id, Workflow.is_template == True)  # noqa: E712
            .all()
        )
        for wf in db_playbooks:
            entries.append({
                "slug": wf.playbook_slug or str(wf.id),
                "name": wf.name,
                "description": "",
                "category": "custom",
                "tags": [],
                "featured": False,
                "source": "user",
            })
    finally:
        db.close()
    return {"count": len(entries), "playbooks": entries}

def get_playbook(ctx, slug: str):
    """Playbook detail — name, description, blocks, inputs, YAML source."""
    from app.routers.playbooks import get_playbook as _get_playbook_route
    try:
        return _get_playbook_route(slug)
    except Exception as e:
        return {"error": str(e), "slug": slug}


# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="list_workflows",
        description="Enumerate workflows in this workspace's org. status = active (default) | archived | all.",
        input_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": ["active", "archived", "all"]},
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("list_workflows"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_run_events",
        description=(
            "Events emitted during one workflow run — block_started/completed/failed, "
            "approval_requested, etc. Use when the user asks 'what happened during run X'."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Run UUID"},
                "kind": {"type": "string", "description": "Filter to one event kind"},
                "limit": _LIMIT,
            },
            "required": ["run_id"],
        },
        impl=_impl("list_run_events"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_workflow_details",
        description=(
            "One workflow's full metadata + latest run status. Match by workflow_id "
            "OR name. Use when the user asks 'what's the status of workflow X'."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "Workflow UUID"},
                "name": {"type": "string", "description": "Workflow name"},
            },
            "required": [],
        },
        impl=_impl("get_workflow_details"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_runs",
        description=(
            "Recent workflow runs across this workspace's org. Filters: "
            "workflow_id, status (pending/running/paused/succeeded/failed/cancelled), "
            "since/until (ISO ts). Returns run_id, workflow_id, workflow_name, "
            "status, started_at, completed_at, triggered_by, actual_turns."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "workflow_id": {"type": "string", "description": "Filter to one workflow"},
                "status": {
                    "type": "string",
                    "enum": ["pending", "running", "paused", "succeeded", "failed", "cancelled"],
                },
                "since": _TS_SINCE, "until": _TS_UNTIL,
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("list_runs"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_run",
        description=(
            "One run's status + timings + outcome payload. Use when the user asks "
            "'what happened in run <id>' or drills into a specific run."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Run UUID"},
            },
            "required": ["run_id"],
        },
        impl=_impl("get_run"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_blocked_workflows",
        description=(
            "Workflows Guard has blocked, ranked by block count. Returns "
            "[{workflow_id, name, block_count, top_rule_id, last_blocked_at}]. "
            "Optional filters: since/until (ISO ts), workflow_id, rule_id."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "since": _TS_SINCE, "until": _TS_UNTIL,
                "workflow_id": {"type": "string", "description": "Filter to one workflow"},
                "rule_id": _RULE_ID,
                "limit": _LIMIT,
            },
            "required": [],
        },
        impl=_impl("get_blocked_workflows"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_playbooks",
        description="Playbook catalog — builtin templates + user-submitted templates. Optional category filter (e.g. 'incident_response', 'ci_cd').",
        input_schema={
            "type": "object",
            "properties": {"category": {"type": "string", "description": "Filter by category slug."}},
            "required": [],
        },
        impl=list_playbooks,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_playbook",
        description="Playbook detail — name, description, blocks, inputs, YAML source.",
        input_schema={
            "type": "object",
            "properties": {"slug": {"type": "string", "description": "Playbook slug (e.g. 'incident_response')."}},
            "required": ["slug"],
        },
        impl=get_playbook,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
