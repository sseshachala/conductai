"""Lens tool registrations — observability_kpis domain.

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
def get_observability_health(ctx):
    """Workspace health strip — active_runs, pending_approvals, stale_workers,
    error_rate_24h. Matches `/observability` header cards."""
    import uuid as _uuid
    from datetime import datetime, timedelta, timezone
    from app.core.database import SessionLocal
    from app.models.run import Run
    from app.routers.insights import STALE_THRESHOLD_MINUTES

    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        now = datetime.now(timezone.utc)
        cutoff_24h = now - timedelta(hours=24)
        stale_cutoff = now - timedelta(minutes=STALE_THRESHOLD_MINUTES)

        base = db.query(Run).filter(Run.workspace_id == ws_uuid)
        active_runs = base.filter(Run.status == "running").count()
        pending = base.filter(Run.status == "paused").count()
        stale = base.filter(Run.status == "running", Run.locked_at < stale_cutoff).count()

        last_24h = base.filter(Run.created_at >= cutoff_24h).all()
        succeeded = sum(1 for r in last_24h if r.status == "succeeded")
        failed = sum(1 for r in last_24h if r.status == "failed")
        total = len(last_24h)
        return {
            "active_runs": active_runs,
            "pending_approvals": pending,
            "stale_workers": stale,
            "succeeded_last_24h": succeeded,
            "failed_last_24h": failed,
            "total_last_24h": total,
            "error_rate_24h": round(failed / total, 3) if total else 0.0,
        }
    finally:
        db.close()

def get_dora_metrics(ctx, days: int = 30):
    """DORA-lite over run_analytics_events — deployment_frequency,
    change_failure_rate, avg_duration_ms, per-trigger breakdown.
    Matches `/observability` DORA-lite quad."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import case, func
    from app.core.database import SessionLocal
    from app.models.run_analytics_event import RunAnalyticsEvent
    from app.routers.insights import _hash_workspace

    db = SessionLocal()
    try:
        ws_hash = _hash_workspace(ctx.workspace_id)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        totals = (
            db.query(
                func.count(RunAnalyticsEvent.id).label("total"),
                func.sum(case((RunAnalyticsEvent.outcome == "succeeded", 1), else_=0)).label("succeeded"),
                func.avg(RunAnalyticsEvent.duration_ms).label("avg_duration"),
            )
            .filter(
                RunAnalyticsEvent.workspace_id == ws_hash,
                RunAnalyticsEvent.created_at >= cutoff,
            )
            .first()
        )
        total = totals.total or 0
        succeeded = int(totals.succeeded or 0)
        failed = total - succeeded
        trigger_rows = (
            db.query(
                RunAnalyticsEvent.trigger_type,
                func.count(RunAnalyticsEvent.id).label("runs"),
                func.sum(case((RunAnalyticsEvent.outcome == "succeeded", 1), else_=0)).label("succeeded"),
            )
            .filter(
                RunAnalyticsEvent.workspace_id == ws_hash,
                RunAnalyticsEvent.created_at >= cutoff,
            )
            .group_by(RunAnalyticsEvent.trigger_type)
            .all()
        )
        by_trigger = {}
        for tr in trigger_rows:
            tr_total = tr.runs or 0
            tr_succeeded = int(tr.succeeded or 0)
            tr_failed = tr_total - tr_succeeded
            by_trigger[tr.trigger_type] = {
                "runs": tr_total,
                "succeeded": tr_succeeded,
                "failed": tr_failed,
                "failure_rate": round(tr_failed / tr_total, 4) if tr_total else 0.0,
            }
        return {
            "window_days": days,
            "total_runs": total,
            "deployment_frequency": round(succeeded / days, 4),
            "change_failure_rate": round(failed / total, 4) if total else 0.0,
            "avg_duration_ms": float(totals.avg_duration) if totals.avg_duration else None,
            "by_trigger": by_trigger,
        }
    finally:
        db.close()

def get_analytics_summary(ctx, days: int = 30):
    """Cost + tokens + top_playbooks + ok/fail totals over the window.
    Matches `/observability` cost summary strip."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import case, func
    from app.core.database import SessionLocal
    from app.models.run_analytics_event import RunAnalyticsEvent
    from app.routers.insights import _hash_workspace, _playbook_stats

    db = SessionLocal()
    try:
        ws_hash = _hash_workspace(ctx.workspace_id)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        totals = db.query(
            func.count(RunAnalyticsEvent.id).label("total"),
            func.sum(case((RunAnalyticsEvent.outcome == "succeeded", 1), else_=0)).label("succeeded"),
            func.sum(RunAnalyticsEvent.cost_usd).label("total_cost"),
            func.sum(RunAnalyticsEvent.input_tokens).label("total_input"),
            func.sum(RunAnalyticsEvent.output_tokens).label("total_output"),
            func.avg(RunAnalyticsEvent.duration_ms).label("avg_duration"),
        ).filter(
            RunAnalyticsEvent.workspace_id == ws_hash,
            RunAnalyticsEvent.created_at >= cutoff,
        ).first()

        total = totals.total or 0
        succeeded = int(totals.succeeded or 0)
        failed = total - succeeded
        top = _playbook_stats(db, ws_hash, cutoff)[:5]
        return {
            "window_days": days,
            "total_runs": total,
            "succeeded": succeeded,
            "failed": failed,
            "success_rate": round(succeeded / total, 3) if total else 0.0,
            "total_cost_usd": float(totals.total_cost or 0),
            "total_input_tokens": int(totals.total_input or 0),
            "total_output_tokens": int(totals.total_output or 0),
            "avg_duration_ms": float(totals.avg_duration) if totals.avg_duration else None,
            "top_playbooks": [p.model_dump() if hasattr(p, "model_dump") else dict(p) for p in top],
        }
    finally:
        db.close()

def list_agent_status(ctx):
    """Live per-agent status rows — health, active/pending/stale, 24h success
    rate, last run. Matches `/observability` agent status grid."""
    import uuid as _uuid
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import func
    from app.core.database import SessionLocal
    from app.models.run import Run
    from app.models.workflow import Workflow, WorkflowVersion
    from app.routers.insights import STALE_THRESHOLD_MINUTES

    db = SessionLocal()
    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
        now = datetime.now(timezone.utc)
        cutoff_24h = now - timedelta(hours=24)
        stale_cutoff = now - timedelta(minutes=STALE_THRESHOLD_MINUTES)

        workflows = (
            db.query(Workflow)
            .filter(Workflow.workspace_id == ws_uuid)
            .order_by(Workflow.name)
            .all()
        )
        result = []
        for wf in workflows:
            version_ids = db.query(WorkflowVersion.id).filter(
                WorkflowVersion.workflow_id == wf.id
            ).subquery()
            runs_24h = (
                db.query(Run)
                .filter(Run.workflow_version_id.in_(version_ids), Run.created_at >= cutoff_24h)
                .all()
            )
            succeeded = sum(1 for r in runs_24h if r.status == "succeeded")
            failed = sum(1 for r in runs_24h if r.status == "failed")
            total = len(runs_24h)
            success_rate = round(succeeded / total, 3) if total else 0.0
            active = sum(1 for r in runs_24h if r.status == "running")
            pending = sum(1 for r in runs_24h if r.status == "paused")
            stale = (
                db.query(func.count(Run.id))
                .filter(
                    Run.workflow_version_id.in_(version_ids),
                    Run.status == "running",
                    Run.locked_at < stale_cutoff,
                )
                .scalar()
            ) or 0
            last_run = (
                db.query(Run)
                .filter(Run.workflow_version_id.in_(version_ids))
                .order_by(Run.created_at.desc())
                .first()
            )
            if stale > 0:
                health = "stale"
            elif total == 0:
                health = "idle"
            elif success_rate < 0.8 or (last_run and last_run.status == "failed"):
                health = "degraded"
            else:
                health = "healthy"
            result.append({
                "workflow_id": str(wf.id),
                "name": wf.name,
                "playbook_slug": wf.playbook_slug,
                "health": health,
                "active_runs": active,
                "pending_approvals": pending,
                "stale_runs": stale,
                "success_rate_24h": success_rate,
                "succeeded_24h": succeeded,
                "failed_24h": failed,
                "last_run_at": last_run.created_at.isoformat() if last_run else None,
                "last_run_status": last_run.status if last_run else None,
            })
        return {"count": len(result), "agents": result}
    finally:
        db.close()

def get_playbook_scorecards(ctx, days: int = 30):
    """Per-playbook grade A–F over the window, from run_online_scores joined
    to run_analytics_events. Matches `/observability` scorecard column."""
    from collections import defaultdict
    from datetime import datetime, timedelta, timezone
    from app.core.database import SessionLocal
    from app.models.run_analytics_event import RunAnalyticsEvent
    from app.models.run_online_score import RunOnlineScore
    from app.routers.insights import _hash_workspace, _pct_to_grade

    db = SessionLocal()
    try:
        ws_hash = _hash_workspace(ctx.workspace_id)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = (
            db.query(
                RunOnlineScore.slug,
                RunOnlineScore.grade,
                RunOnlineScore.pct,
                RunOnlineScore.mechanical_score,
                RunOnlineScore.mechanical_max,
                RunOnlineScore.judge_score,
                RunOnlineScore.judge_max,
                RunOnlineScore.judge_used,
            )
            .join(RunAnalyticsEvent, RunOnlineScore.run_id == RunAnalyticsEvent.run_id)
            .filter(
                RunAnalyticsEvent.workspace_id == ws_hash,
                RunAnalyticsEvent.created_at >= cutoff,
            )
            .all()
        )
        buckets: dict[str, list] = defaultdict(list)
        for r in rows:
            buckets[r.slug].append(r)

        result = []
        for slug, entries in buckets.items():
            rc = len(entries)
            avg_pct = round(sum(float(e.pct) for e in entries) / rc, 2)
            grade_dist = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
            for e in entries:
                g = e.grade if e.grade in grade_dist else "F"
                grade_dist[g] += 1
            tm_score = sum(e.mechanical_score for e in entries)
            tm_max = sum(e.mechanical_max for e in entries)
            avg_mech = round(tm_score / tm_max * 100 if tm_max > 0 else 0.0, 2)
            judge_entries = [e for e in entries if e.judge_used]
            if judge_entries:
                tj_score = sum(e.judge_score for e in judge_entries)
                tj_max = sum(e.judge_max for e in judge_entries)
                avg_judge = round(tj_score / tj_max * 100 if tj_max > 0 else 0.0, 2)
            else:
                avg_judge = 0.0
            result.append({
                "playbook_slug": slug,
                "run_count": rc,
                "avg_pct": avg_pct,
                "grade": _pct_to_grade(avg_pct),
                "grade_dist": grade_dist,
                "avg_mechanical": avg_mech,
                "avg_judge": avg_judge,
            })
        result.sort(key=lambda x: x["avg_pct"], reverse=True)
        return {"window_days": days, "count": len(result), "scorecards": result}
    finally:
        db.close()


_DAYS_WINDOW = {"type": "integer", "minimum": 1, "maximum": 365, "description": "Window in days"}
_TIME_WINDOW = {
    "type": "string",
    "description": "Symbolic time window — last_24h, last_7d, mtd",
}


# ── ToolDef list ───────────────────────────────────────────────────────
TOOLS: list[ToolDef] = [
    ToolDef(
        name="get_observability_health",
        description="Workspace health strip — active_runs, pending_approvals, stale_workers, error_rate_24h. Matches /observability header cards.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=get_observability_health,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_dora_metrics",
        description="DORA-lite — deployment_frequency, change_failure_rate, avg_duration_ms + per-trigger breakdown. Matches /observability DORA quad.",
        input_schema={"type": "object", "properties": {"days": _DAYS_WINDOW}, "required": []},
        impl=get_dora_metrics,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_analytics_summary",
        description="Cost + tokens + top_playbooks + ok/fail totals over the last N days. Matches /observability cost summary strip.",
        input_schema={"type": "object", "properties": {"days": _DAYS_WINDOW}, "required": []},
        impl=get_analytics_summary,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="list_agent_status",
        description="Live per-agent status rows — health (healthy/degraded/stale/idle), active/pending/stale run counts, 24h success rate. Matches /observability agent grid.",
        input_schema={"type": "object", "properties": {}, "required": []},
        impl=list_agent_status,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
    ToolDef(
        name="get_playbook_scorecards",
        description="Per-playbook grade A–F over the last N days, with grade distribution + mechanical/judge component averages. Matches /observability scorecards.",
        input_schema={"type": "object", "properties": {"days": _DAYS_WINDOW}, "required": []},
        impl=get_playbook_scorecards,
        annotations=_READ_ONLY,
        tags=_LENS_TAGS,
    ),
]
