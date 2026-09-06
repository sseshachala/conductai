"""#1450 PR 4 — Lens actor: save a report layout to the workspace.

Two-step: `propose` validates name / widgets / slug (auto-derived from
name if not passed) and rejects on conflict; `execute` writes the row to
`workspace_report_layouts` — same INSERT as `POST /workspaces/{ws}/report-layouts`.

Return payload includes the `/lens/report-builder?slug=X` URL so the
chat surface can render a clickable link on confirm.

Report shape emerges from the widget count:
- 1 widget  → "Basic" (one-widget quick share)
- 2+ widgets → "Operational" / "Observability" / custom

The tool doesn't care about shape — it's an LLM-side prompt concept.
"""
from __future__ import annotations

import re
import uuid as _uuid
from datetime import datetime, timezone
from typing import Any

import structlog

from app.modules.glens.actor.registry import default_action_registry
from app.modules.glens.actor.types import ActionCtx, ActionSpec, ProposeResult

log = structlog.get_logger()


_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_VALID_HINTS = {"kpi_card", "spark", "list", "table", "agent_row"}


def _slugify(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:64]


def _validate_widgets(raw: Any) -> tuple[list[dict[str, str]] | None, str | None]:
    """Return (normalized, error) — normalized is a list of {tool_name, hint}."""
    if not isinstance(raw, list) or not raw:
        return None, "layout_spec must be a non-empty list"
    from app.tools.registry import default_registry

    valid_tools = {t.name for t in default_registry.list(tag="widget")}
    out: list[dict[str, str]] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            return None, f"layout_spec[{i}] must be an object"
        tool_name = str(entry.get("tool_name") or "").strip()
        hint = str(entry.get("hint") or "").strip()
        if not tool_name:
            return None, f"layout_spec[{i}].tool_name required"
        if tool_name not in valid_tools:
            return None, f"layout_spec[{i}].tool_name '{tool_name}' is not a widget-tagged tool"
        if hint not in _VALID_HINTS:
            return None, f"layout_spec[{i}].hint must be one of {sorted(_VALID_HINTS)}"
        out.append({"tool_name": tool_name, "hint": hint})
    return out, None


def _propose_report(ctx: ActionCtx, args: dict[str, Any]) -> ProposeResult:
    name = str(args.get("name") or "").strip()
    if not name:
        return ProposeResult(rejected=True, reason="name required", summary="", resolved_input={})
    if len(name) > 200:
        return ProposeResult(rejected=True, reason="name too long (max 200)", summary="", resolved_input={})

    slug_arg = args.get("slug")
    slug = str(slug_arg).strip().lower() if slug_arg else _slugify(name)
    if not _SLUG_RE.match(slug):
        return ProposeResult(
            rejected=True,
            reason="slug must match ^[a-z0-9][a-z0-9-]{0,63}$",
            summary="", resolved_input={},
        )

    widgets, err = _validate_widgets(args.get("layout_spec"))
    if err or widgets is None:
        return ProposeResult(rejected=True, reason=err or "invalid widgets",
                             summary="", resolved_input={})

    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
    except ValueError:
        return ProposeResult(rejected=True, reason="Invalid workspace",
                             summary="", resolved_input={})

    from app.models.workspace_report_layout import WorkspaceReportLayout

    existing = (
        ctx.db.query(WorkspaceReportLayout)
        .filter(
            WorkspaceReportLayout.workspace_id == ws_uuid,
            WorkspaceReportLayout.slug == slug,
        )
        .first()
    )
    if existing:
        return ProposeResult(
            rejected=True,
            reason=f"A report with slug '{slug}' already exists in this workspace (name: '{existing.name}')",
            summary="", resolved_input={},
        )

    summary = f"Save report '{name}' as /{slug} with {len(widgets)} widget(s)"
    return ProposeResult(
        summary=summary,
        resolved_input={"name": name, "slug": slug, "layout_spec": widgets},
    )


def _execute_report(ctx: ActionCtx, resolved: dict[str, Any]) -> dict[str, Any]:
    from app.models.workspace_report_layout import WorkspaceReportLayout

    ws_uuid = _uuid.UUID(ctx.workspace_id)
    now = datetime.now(timezone.utc)

    row = WorkspaceReportLayout(
        id=_uuid.uuid4(),
        workspace_id=ws_uuid,
        slug=resolved["slug"],
        name=resolved["name"],
        layout_spec=resolved["layout_spec"],
        created_by=ctx.clerk_user_id or "lens.actor",
        created_at=now,
        updated_at=now,
    )
    ctx.db.add(row)
    ctx.db.commit()

    return {
        "id": str(row.id),
        "slug": row.slug,
        "name": row.name,
        "widgets_count": len(resolved["layout_spec"]),
        "url": f"/lens/report-builder?slug={row.slug}",
        "saved": True,
    }


default_action_registry.register(ActionSpec(
    name="propose_report",
    guard_permission="platform.workflows.edit",
    propose=_propose_report,
    execute=_execute_report,
    description=(
        "Save a report layout to the workspace. Two-step: returns a "
        "pending action for the user to confirm; the confirm click "
        "inserts the workspace_report_layouts row and returns the "
        "/lens/report-builder?slug=X URL."
    ),
))
