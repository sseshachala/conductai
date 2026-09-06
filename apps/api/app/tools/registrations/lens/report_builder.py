"""Lens tool registrations — report_builder domain (#1450 PR 4).

Three tools that let Lens compose and save a report layout via chat:

- `list_report_widgets` — read: catalog of widget-tagged tools + hints.
- `list_report_templates` — read: 2 starter templates (Operations,
  Observability). "Basic" (one-widget quick share) is not a static
  template — Lens picks 1 widget for the ask and calls propose_report.
- `propose_report` — actor: two-step confirm; writes to
  `workspace_report_layouts`. Returns the `/lens/report-builder?slug=X`
  URL on confirm so chat can render a clickable link.

Prompt hint: when the user says "build me a report" without specifying,
Lens offers three shapes — Basic, Operational, Observability. Basic maps
to a 1-widget report chosen from `list_report_widgets`; the other two
seed from `list_report_templates`.
"""
from __future__ import annotations

from typing import Any

from app.tools.registrations.lens._shared import _actor_impl, _ACTOR_TAGS, _LENS_TAGS
from app.tools.types import ToolAnnotations, ToolDef


# ── Static template registry (mirror of apps/web/src/lib/reportBuilder/templates.ts)
#
# ponytail: duplicated across TS + Python. The two files change rarely
# and are small enough that a shared JSON isn't worth wiring. If the
# template set grows beyond ~5, hoist to a single JSON both sides read.
_TEMPLATES: list[dict[str, Any]] = [
    {
        "slug": "operations",
        "name": "Operations",
        "description": "Day-to-day agent output — outcomes, attention, health, token usage, policy hits.",
        "widgets": [
            {"tool_name": "get_dashboard_outcomes",    "hint": "kpi_card"},
            {"tool_name": "list_attention_runs",       "hint": "list"},
            {"tool_name": "list_agent_health",         "hint": "agent_row"},
            {"tool_name": "get_dashboard_token_usage", "hint": "spark"},
            {"tool_name": "get_top_policy_hits",       "hint": "table"},
        ],
    },
    {
        "slug": "observability",
        "name": "Observability",
        "description": "Platform health — DORA, analytics, agent status, playbook scorecards.",
        "widgets": [
            {"tool_name": "get_observability_health",  "hint": "kpi_card"},
            {"tool_name": "get_dora_metrics",          "hint": "kpi_card"},
            {"tool_name": "get_analytics_summary",     "hint": "spark"},
            {"tool_name": "list_agent_status",         "hint": "list"},
            {"tool_name": "get_playbook_scorecards",   "hint": "table"},
        ],
    },
]


# ── Free-function tool impls ────────────────────────────────────────────────

def list_report_widgets(ctx) -> dict[str, Any]:  # noqa: ARG001
    """Return the widget catalog — every tool tagged `widget` with its render hint.

    Lens uses this to pick a widget for the "Basic" (one-widget) report
    shape, or to add extra widgets on top of a template.
    """
    from app.tools.registry import default_registry

    widgets = []
    for t in default_registry.list(tag="widget"):
        hint = next((tag.split(":", 1)[1] for tag in t.tags if tag.startswith("hint:")), None)
        widgets.append({
            "tool_name": t.name,
            "hint": hint,
            "description": t.description,
        })
    return {"widgets": widgets, "count": len(widgets)}


def list_report_templates(ctx) -> dict[str, Any]:  # noqa: ARG001
    """Return the 2 static report templates (Operations, Observability).

    Lens uses these to seed multi-widget reports on shape choice. The
    "Basic" shape (one widget) is not a template — pick a widget from
    `list_report_widgets` instead.
    """
    return {"templates": _TEMPLATES, "count": len(_TEMPLATES)}


TOOLS: list[ToolDef] = [
    ToolDef(
        name="list_report_widgets",
        description=(
            "List every widget-tagged tool with its render hint — the catalog Lens "
            "picks from when composing a report. Use for the 'Basic' one-widget "
            "shape, or when adding widgets on top of a template. Read-only."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=list_report_widgets,
        annotations=ToolAnnotations(read_only=True),
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_report_templates",
        description=(
            "List the static report templates (Operations, Observability). Each "
            "template is an ordered widget list Lens can pass straight to "
            "propose_report. Basic (one-widget) is not a template — pick from "
            "list_report_widgets instead."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=list_report_templates,
        annotations=ToolAnnotations(read_only=True),
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="propose_report",
        description=(
            "Save a workspace report layout. Two-step: returns a pending action "
            "for the user to confirm; the confirm click inserts the row and "
            "returns the /lens/report-builder?slug=X URL. Slug is optional — "
            "auto-derived from name if omitted. Fails on slug conflict; retry "
            "with a different slug or reuse the existing report."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable report name, e.g. 'Ops Overview'.",
                },
                "layout_spec": {
                    "type": "array",
                    "description": "Ordered widget list. Each item = {tool_name, hint}.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool_name": {"type": "string"},
                            "hint": {
                                "type": "string",
                                "enum": ["kpi_card", "spark", "list", "table", "agent_row"],
                            },
                        },
                        "required": ["tool_name", "hint"],
                    },
                },
                "slug": {
                    "type": "string",
                    "description": "Optional URL slug. Auto-derived from name if omitted.",
                },
            },
            "required": ["name", "layout_spec"],
        },
        impl=_actor_impl("propose_report"),
        annotations=ToolAnnotations(read_only=False, destructive=False, idempotent=False),
        tags=_ACTOR_TAGS,
    ),
]
