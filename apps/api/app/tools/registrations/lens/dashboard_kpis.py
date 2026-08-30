"""Lens tool registrations — dashboard_kpis domain.

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
def get_dashboard_outcomes(ctx, time_window: str = "last_7d"):
    """Outcome rollup — PRs / issues / reviews / incidents + ok/fail counts.
    Matches the /dashboard header (`OutcomeStats`)."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.run import Run
    from app.models.workflow import Workflow, WorkflowVersion
    from app.routers.insights import _outcome_type

    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        since = _window_start(time_window)
        rows = (
            db.query(Run, Workflow.playbook_slug.label("slug"))
            .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
            .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
            .filter(Workflow.workspace_id == ws_uuid, Run.created_at >= since)
            .all()
        )
        prs = issues = reviews = incidents = ok = fail = 0
        for run, slug in rows:
            if run.status == "succeeded":
                ok += 1
                ot = _outcome_type(run, slug)
                if ot == "pr_opened":
                    prs += 1
                elif ot == "issue_triaged":
                    issues += 1
                elif ot == "review_completed":
                    reviews += 1
                elif ot == "incident_investigated":
                    incidents += 1
            elif run.status == "failed":
                fail += 1
        return {
            "time_window": time_window,
            "since": since.isoformat(),
            "prs_opened": prs,
            "issues_triaged": issues,
            "reviews_completed": reviews,
            "incidents_investigated": incidents,
            "successful_automations": ok,
            "failed_automations": fail,
        }
    finally:
        db.close()

def list_attention_runs(ctx, limit: int = 10):
    """Runs needing attention — failed / paused / cancelled, newest first.
    Matches `/dashboard` needs_attention block."""
    import uuid as _uuid
    from app.core.database import SessionLocal
    from app.models.run import Run
    from app.models.workflow import Workflow, WorkflowVersion
    from app.routers.insights import ATTENTION_STATUSES, _extract_repo
    from app.schemas.run import _extract_trigger_summary

    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        rows = (
            db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"))
            .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
            .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
            .filter(
                Workflow.workspace_id == ws_uuid,
                Run.status.in_(ATTENTION_STATUSES),
            )
            .order_by(Run.created_at.desc())
            .limit(limit)
            .all()
        )
        return {
            "count": len(rows),
            "runs": [
                {
                    "run_id": str(run.id),
                    "workflow_id": str(wf_id),
                    "workflow_name": wf_name,
                    "status": run.status,
                    "triggered_by": run.triggered_by,
                    "trigger_summary": _extract_trigger_summary(run.state),
                    "created_at": run.created_at.isoformat(),
                    "repo": _extract_repo(run.state),
                }
                for run, wf_id, wf_name in rows
            ],
        }
    finally:
        db.close()

def list_agent_health(ctx):
    """All-time per-agent aggregate — run_count, success_rate, last_run.
    Matches `/dashboard` agent_health block."""
    import uuid as _uuid
    from sqlalchemy import case, func
    from app.core.database import SessionLocal
    from app.models.run import Run
    from app.models.workflow import Workflow, WorkflowVersion

    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        agg = (
            db.query(
                Workflow.id.label("wf_id"),
                Workflow.name.label("wf_name"),
                Workflow.playbook_slug,
                func.count(Run.id).label("run_count"),
                func.sum(case((Run.status == "succeeded", 1), else_=0)).label("succeeded"),
                func.sum(case((Run.status == "failed", 1), else_=0)).label("failed"),
                func.max(Run.created_at).label("last_run_at"),
            )
            .join(WorkflowVersion, WorkflowVersion.workflow_id == Workflow.id)
            .outerjoin(Run, Run.workflow_version_id == WorkflowVersion.id)
            .filter(Workflow.workspace_id == ws_uuid)
            .group_by(Workflow.id, Workflow.name, Workflow.playbook_slug)
            .order_by(func.max(Run.created_at).desc().nullslast())
            .all()
        )

        # Per-workflow last_run_status — same pattern as insights.get_dashboard.
        wf_ids = [row.wf_id for row in agg]
        last_status_map: dict[str, str] = {}
        if wf_ids:
            max_run_sq = (
                db.query(
                    WorkflowVersion.workflow_id.label("wf_id"),
                    func.max(Run.created_at).label("max_at"),
                )
                .join(Run, Run.workflow_version_id == WorkflowVersion.id)
                .filter(WorkflowVersion.workflow_id.in_(wf_ids))
                .group_by(WorkflowVersion.workflow_id)
                .subquery()
            )
            last_runs = (
                db.query(WorkflowVersion.workflow_id.label("wf_id"), Run.status)
                .join(Run, Run.workflow_version_id == WorkflowVersion.id)
                .join(
                    max_run_sq,
                    (WorkflowVersion.workflow_id == max_run_sq.c.wf_id)
                    & (Run.created_at == max_run_sq.c.max_at),
                )
                .all()
            )
            last_status_map = {str(r.wf_id): r.status for r in last_runs}

        agents = []
        for row in agg:
            rc = row.run_count or 0
            sc = row.succeeded or 0
            fc = row.failed or 0
            agents.append({
                "workflow_id": str(row.wf_id),
                "name": row.wf_name,
                "playbook_slug": row.playbook_slug,
                "run_count": rc,
                "succeeded_count": sc,
                "failed_count": fc,
                "success_rate": round((sc / rc) * 100, 1) if rc else 0.0,
                "last_run_status": last_status_map.get(str(row.wf_id)),
                "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
            })
        return {"count": len(agents), "agents": agents}
    finally:
        db.close()

def get_dashboard_token_usage(ctx):
    """All-time token totals + per-agent breakdown from RunTrace rows.
    Matches `/dashboard` token_usage block."""
    import uuid as _uuid
    from sqlalchemy import func
    from app.core.database import SessionLocal
    from app.models.run import Run
    from app.models.workflow import Workflow, WorkflowVersion
    from app.models.run_trace import RunTrace
    from app.routers.insights import _INPUT_COST_PER_M, _OUTPUT_COST_PER_M

    def _cost(inp: int, out: int) -> float:
        return round((inp * _INPUT_COST_PER_M + out * _OUTPUT_COST_PER_M) / 1_000_000, 4)

    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        rows = (
            db.query(
                Workflow.id.label("wf_id"),
                Workflow.name.label("wf_name"),
                func.coalesce(func.sum(RunTrace.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(RunTrace.output_tokens), 0).label("output_tokens"),
            )
            .join(WorkflowVersion, WorkflowVersion.workflow_id == Workflow.id)
            .join(Run, Run.workflow_version_id == WorkflowVersion.id)
            .join(RunTrace, RunTrace.run_id == Run.id)
            .filter(Workflow.workspace_id == ws_uuid)
            .group_by(Workflow.id, Workflow.name)
            .order_by(func.sum(RunTrace.input_tokens + RunTrace.output_tokens).desc().nullslast())
            .all()
        )
        by_agent = [
            {
                "workflow_id": str(row.wf_id),
                "name": row.wf_name,
                "input_tokens": row.input_tokens,
                "output_tokens": row.output_tokens,
                "total_tokens": row.input_tokens + row.output_tokens,
                "estimated_cost_usd": _cost(row.input_tokens, row.output_tokens),
            }
            for row in rows
        ]
        ti = sum(a["input_tokens"] for a in by_agent)
        to = sum(a["output_tokens"] for a in by_agent)
        return {
            "total_input_tokens": ti,
            "total_output_tokens": to,
            "total_tokens": ti + to,
            "estimated_cost_usd": _cost(ti, to),
            "by_agent": by_agent,
        }
    finally:
        db.close()

def get_top_policy_hits(ctx, limit: int = 5, days: int = 30):
    """Guard policy hit leaderboard — blocked-only rule_id counts over the
    trailing N days. Matches `/dashboard` guard_snapshot.top_policy_hits."""
    import uuid as _uuid
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func
    from app.core.database import SessionLocal
    from app.modules.guard.models import GuardAuditEvent

    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        since = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (
            db.query(GuardAuditEvent.rule_id, func.count(GuardAuditEvent.id).label("cnt"))
            .filter(
                GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.decision == "blocked",
                GuardAuditEvent.rule_id.isnot(None),
                GuardAuditEvent.ts >= since,
            )
            .group_by(GuardAuditEvent.rule_id)
            .order_by(func.count(GuardAuditEvent.id).desc())
            .limit(limit)
            .all()
        )
        return {
            "window_days": days,
            "hits": [{"policy_name": r.rule_id, "count": r.cnt} for r in rows],
        }
    finally:
        db.close()


# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_dashboard_outcomes",
        description="Workspace outcome rollup — PRs opened, issues triaged, reviews completed, incidents investigated, succeeded/failed automations. Matches /dashboard header.",
        input_schema={"type": "object", "properties": {"time_window": _TIME_WINDOW}, "required": []},
        impl=get_dashboard_outcomes,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_attention_runs",
        description="Runs needing attention — failed, paused, or cancelled — newest first. Matches /dashboard needs_attention block.",
        input_schema={"type": "object", "properties": {"limit": _LIMIT}, "required": []},
        impl=list_attention_runs,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_agent_health",
        description="All-time per-agent aggregate — run count, success rate, last run status. Matches /dashboard agent_health block.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=list_agent_health,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_dashboard_token_usage",
        description="All-time token totals + per-agent breakdown + estimated cost. Matches /dashboard token_usage block.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_dashboard_token_usage,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_top_policy_hits",
        description="Guard policy hit leaderboard — blocked-only rule_id counts over the last N days. Matches /dashboard guard_snapshot.top_policy_hits.",
        input_schema={
            "type": "object",
            "properties": {"limit": _LIMIT, "days": _DAYS_WINDOW},
            "required": [],
        },
        impl=get_top_policy_hits,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
