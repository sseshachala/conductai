"""Lens tool registrations — governance domain.

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
def _run_framework_coverage(workspace_id: str):
    from app.core.database import SessionLocal
    from app.routers.governance import _compute_framework_coverage
    db = SessionLocal()
    try:
        return _compute_framework_coverage(db, workspace_id)
    finally:
        db.close()

def get_governance_summary(ctx):
    """Full framework coverage matrix — installed + bonus + rules totals."""
    return _run_framework_coverage(ctx.workspace_id).model_dump()

def get_soc2_status(ctx, framework: str = "SOC2"):
    """Rollup for a single compliance framework. Defaults to SOC2. Returns
    installed status + rules + controls + recommended pack for uninstalled."""
    from app.routers.governance import RECOMMENDED_PACK
    result = _run_framework_coverage(ctx.workspace_id)
    fw = framework.upper()
    for row in result.installed:
        if row.framework == fw:
            return {"status": "installed", **row.model_dump()}
    for row in result.bonus:
        if row.framework == fw:
            return {"status": "bonus", **row.model_dump()}
    return {
        "status": "not_covered",
        "framework": fw,
        "rules_count": 0,
        "controls": [],
        "packs": [],
        "recommended_pack": RECOMMENDED_PACK.get(fw),
    }

def get_ai_rollout_status(ctx):
    """AI rollout instructions published for the workspace — published flag,
    content length, version, last update, publisher."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.workspace_instructions import WorkspaceInstructions
    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        row = db.query(WorkspaceInstructions).filter(
            WorkspaceInstructions.workspace_id == ws_uuid
        ).first()
        if row is None:
            return {
                "published": False,
                "content_length": 0,
                "version": None,
                "updated_at": None,
                "updated_by": None,
            }
        return {
            "published": True,
            "content_length": len(row.content or ""),
            "version": row.version,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "updated_by": row.updated_by,
        }
    finally:
        db.close()


# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_compliance_status",
        description="ASI-01..10 compliance scorecard for this workspace (grade, score, per-control status).",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_compliance_status"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_governance_kpis",
        description="Governance KPIs — events today, blocks today, active devs today, blocks MTD, risk avoided MTD.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_governance_kpis"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_framework_coverage",
        description="Installed compliance packs and rules count per framework (OWASP, SOC2, HIPAA, etc.).",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_framework_coverage"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_governance_narrative",
        description="LLM-generated governance narrative for the workspace. Calls the configured LLM provider.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=_impl("get_governance_narrative"),
        annotations=_READ_ONLY_OPEN_WORLD,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_recent_governance_events",
        description="Recent governance-relevant audit events (blocked, warned, audited by default).",
        input_schema={
            "type": "object",
            "properties": {
                "limit": _LIMIT, "decision": _DECISION,
                "since": _TS_SINCE, "until": _TS_UNTIL,
            },
            "required": [],
        },
        impl=_impl("get_recent_governance_events"),
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_governance_summary",
        description="Full framework coverage matrix — installed frameworks, bonus (cross-tag) coverage, and rules totals.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_governance_summary,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_soc2_status",
        description="Rollup for one compliance framework (defaults to SOC2). Returns installed status + rules + controls + recommended pack.",
        input_schema={
            "type": "object",
            "properties": {
                "framework": {
                    "type": "string",
                    "description": "Framework name: SOC2, HIPAA, OWASP, PCI_DSS, ISO_42001, GDPR, EU_AI_ACT, NIST, NIS2, DORA.",
                },
            },
            "required": [],
        },
        impl=get_soc2_status,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_ai_rollout_status",
        description="AI rollout instructions published for the workspace — published flag, content length, version, last update.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_ai_rollout_status,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
