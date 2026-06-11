"""
insights router — merges dashboard, analytics, and observability endpoints.

All endpoints keep their original full paths; only the module is consolidated.

dashboard endpoints:
  GET /dashboard

analytics endpoints:
  GET /analytics/summary
  GET /analytics/playbooks
  GET /analytics/runs
  GET /analytics/scorecards
  GET /analytics/dora

observability endpoints:
  GET  /observability/summary
  GET  /observability/agents
  GET  /observability/stream
  GET  /observability/alerts
  POST /observability/alerts/{id}/resolve
"""
import asyncio
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_permission
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.models.run import Run
from app.models.run_analytics_event import RunAnalyticsEvent
from app.models.run_online_score import RunOnlineScore
from app.models.run_trace import RunTrace
from app.models.watchdog_event import WatchdogEvent
from app.models.workflow import Workflow, WorkflowVersion
from app.modules.guard.models import GuardAuditEvent
from app.routers.runs import get_workspace_id_sse, require_workspace_role_sse
from app.schemas.run import _extract_trigger_summary

router = APIRouter(tags=["insights"])


# ══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════════════════

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════
# Dashboard
# ══════════════════════════════════════════════════════════════════════════════

"""
GET /dashboard  — outcome-based summary for the workspace.

Outcome counting strategy (COALESCE, no regression):
  1. If run.outcome is set (new runs), read outcome["type"] directly.
  2. If run.outcome is NULL (pre-migration runs), fall back to state heuristics.
This means historical metrics never drop to zero during rollout.
"""

def _extract_repo(state: dict | None) -> str | None:
    if not state:
        return None
    trigger = state.get("_trigger") or {}
    return (trigger.get("repository") or {}).get("full_name") or None


# Sonnet pricing (per 1M tokens) used for cost estimates — approximate
_INPUT_COST_PER_M  = 3.0
_OUTPUT_COST_PER_M = 15.0

# Statuses that need human attention — mirrors runUtils.needsAttention()
ATTENTION_STATUSES = ["failed", "paused", "cancelled"]

# Playbook slugs that produce each outcome type (used for heuristic fallback)
_REVIEW_SLUGS   = {"pr_reviewer", "copilot_reviewer", "security_scanner"}
_INCIDENT_SLUGS = {"incident_responder", "postmortem_drafter"}
_TRIAGE_SLUGS   = {"issue_triage"}
_PR_SLUGS       = {"autopilot_quick", "autopilot_full", "autopilot_approved",
                   "security_patch_updater", "dependency_updater"}


def _outcome_type(run: Run, slug: str | None) -> str | None:
    """
    Return the semantic outcome type for a run.
    Reads run.outcome["type"] if set (new runs), otherwise falls back to heuristics.
    """
    if run.outcome and isinstance(run.outcome, dict):
        return run.outcome.get("type")

    # Heuristic fallback for pre-migration runs (outcome column is NULL)
    if run.status != "succeeded":
        return None
    state = run.state or {}

    def _find(key: str) -> bool:
        if state.get(key):
            return True
        return any(isinstance(v, dict) and v.get(key) for v in state.values())

    if slug in _PR_SLUGS and (_find("pr_url")):
        return "pr_opened"
    if slug in _REVIEW_SLUGS:
        return "review_completed"
    if slug in _TRIAGE_SLUGS:
        return "issue_triaged"
    if slug in _INCIDENT_SLUGS:
        return "incident_investigated"
    return None


class OutcomeStats(BaseModel):
    prs_opened: int
    issues_triaged: int
    reviews_completed: int
    incidents_investigated: int
    successful_automations: int
    failed_automations: int


class AgentHealth(BaseModel):
    workflow_id: str
    name: str
    playbook_slug: str | None
    run_count: int
    succeeded_count: int
    failed_count: int
    success_rate: float
    last_run_status: str | None
    last_run_at: str | None


class AttentionRun(BaseModel):
    run_id: str
    workflow_id: str
    workflow_name: str
    status: str
    triggered_by: str | None
    trigger_summary: str | None
    created_at: str
    repo: str | None = None


class RecentRun(BaseModel):
    run_id: str
    workflow_id: str
    workflow_name: str
    status: str
    triggered_by: str | None
    started_at: str | None
    created_at: str
    repo: str | None = None


class AgentTokenUsage(BaseModel):
    workflow_id: str
    name: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float


class TokenUsage(BaseModel):
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    by_agent: list[AgentTokenUsage]


class DashboardOut(BaseModel):
    outcomes: OutcomeStats
    needs_attention: list[AttentionRun]
    agent_health: list[AgentHealth]
    recent_activity: list[RecentRun]
    token_usage: TokenUsage
    guard_blocks_today: int


@router.get("/dashboard", response_model=DashboardOut)
def get_dashboard(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.runs.view")),
):
    today_midnight = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = datetime.now(timezone.utc) - timedelta(days=7)

    # ── Week runs with playbook_slug for COALESCE outcome resolution ──────────
    week_rows = (
        db.query(Run, Workflow.playbook_slug.label("slug"))
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .filter(Workflow.workspace_id == workspace_id, Run.created_at >= week_start)
        .all()
    )

    prs_opened = issues_triaged = reviews_completed = incidents_investigated = 0
    successful_automations = failed_automations = 0

    for run, slug in week_rows:
        if run.status == "succeeded":
            successful_automations += 1
            ot = _outcome_type(run, slug)
            if ot == "pr_opened":
                prs_opened += 1
            elif ot == "issue_triaged":
                issues_triaged += 1
            elif ot == "review_completed":
                reviews_completed += 1
            elif ot == "incident_investigated":
                incidents_investigated += 1
        elif run.status == "failed":
            failed_automations += 1

    outcomes = OutcomeStats(
        prs_opened=prs_opened,
        issues_triaged=issues_triaged,
        reviews_completed=reviews_completed,
        incidents_investigated=incidents_investigated,
        successful_automations=successful_automations,
        failed_automations=failed_automations,
    )

    # ── Needs Attention — failed/paused/cancelled, aligned with runUtils ──────
    attention_rows = (
        db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"))
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .filter(
            Workflow.workspace_id == workspace_id,
            Run.status.in_(ATTENTION_STATUSES),
        )
        .order_by(Run.created_at.desc())
        .limit(10)
        .all()
    )

    needs_attention = [
        AttentionRun(
            run_id=str(run.id),
            workflow_id=str(wf_id),
            workflow_name=wf_name,
            status=run.status,
            triggered_by=run.triggered_by,
            trigger_summary=_extract_trigger_summary(run.state),
            created_at=run.created_at.isoformat(),
            repo=_extract_repo(run.state),
        )
        for run, wf_id, wf_name in attention_rows
    ]

    # ── Agent Health — all-time aggregation ──────────────────────────────────
    wf_agg = (
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
        .filter(Workflow.workspace_id == workspace_id)
        .group_by(Workflow.id, Workflow.name, Workflow.playbook_slug)
        .order_by(func.max(Run.created_at).desc().nullslast())
        .all()
    )

    wf_ids = [row.wf_id for row in wf_agg]
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
        last_status_map = {str(row.wf_id): row.status for row in last_runs}

    agent_health = []
    for row in wf_agg:
        rc = row.run_count or 0
        sc = row.succeeded or 0
        fc = row.failed or 0
        rate = round((sc / rc) * 100, 1) if rc else 0.0
        agent_health.append(AgentHealth(
            workflow_id=str(row.wf_id),
            name=row.wf_name,
            playbook_slug=row.playbook_slug,
            run_count=rc,
            succeeded_count=sc,
            failed_count=fc,
            success_rate=rate,
            last_run_status=last_status_map.get(str(row.wf_id)),
            last_run_at=row.last_run_at.isoformat() if row.last_run_at else None,
        ))

    # ── Recent Activity — last 5 runs ────────────────────────────────────────
    recent_rows = (
        db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"))
        .join(WorkflowVersion, WorkflowVersion.id == Run.workflow_version_id)
        .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .filter(Workflow.workspace_id == workspace_id)
        .order_by(Run.created_at.desc())
        .limit(5)
        .all()
    )

    recent_activity = [
        RecentRun(
            run_id=str(run.id),
            workflow_id=str(wf_id),
            workflow_name=wf_name,
            status=run.status,
            triggered_by=run.triggered_by,
            started_at=run.started_at.isoformat() if run.started_at else None,
            created_at=run.created_at.isoformat(),
            repo=_extract_repo(run.state),
        )
        for run, wf_id, wf_name in recent_rows
    ]

    # ── Token usage — all-time, aggregated from run_traces ───────────────────
    token_rows = (
        db.query(
            Workflow.id.label("wf_id"),
            Workflow.name.label("wf_name"),
            func.coalesce(func.sum(RunTrace.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(RunTrace.output_tokens), 0).label("output_tokens"),
        )
        .join(WorkflowVersion, WorkflowVersion.workflow_id == Workflow.id)
        .join(Run, Run.workflow_version_id == WorkflowVersion.id)
        .join(RunTrace, RunTrace.run_id == Run.id)
        .filter(Workflow.workspace_id == workspace_id)
        .group_by(Workflow.id, Workflow.name)
        .order_by(func.sum(RunTrace.input_tokens + RunTrace.output_tokens).desc().nullslast())
        .all()
    )

    def _cost(inp: int, out: int) -> float:
        return round((inp * _INPUT_COST_PER_M + out * _OUTPUT_COST_PER_M) / 1_000_000, 4)

    by_agent = [
        AgentTokenUsage(
            workflow_id=str(row.wf_id),
            name=row.wf_name,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            total_tokens=row.input_tokens + row.output_tokens,
            estimated_cost_usd=_cost(row.input_tokens, row.output_tokens),
        )
        for row in token_rows
    ]
    total_input  = sum(a.input_tokens for a in by_agent)
    total_output = sum(a.output_tokens for a in by_agent)
    token_usage = TokenUsage(
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_tokens=total_input + total_output,
        estimated_cost_usd=_cost(total_input, total_output),
        by_agent=by_agent,
    )

    # ── Guard blocks today — count "blocked" audit events since midnight UTC ──
    guard_blocks_today: int = (
        db.query(func.count(GuardAuditEvent.id))
        .filter(
            GuardAuditEvent.workspace_id == workspace_id,
            GuardAuditEvent.decision == "blocked",
            GuardAuditEvent.ts >= today_midnight,
        )
        .scalar()
        or 0
    )

    return DashboardOut(
        outcomes=outcomes,
        needs_attention=needs_attention,
        agent_health=agent_health,
        recent_activity=recent_activity,
        token_usage=token_usage,
        guard_blocks_today=guard_blocks_today,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Analytics
# ══════════════════════════════════════════════════════════════════════════════

"""
Analytics API — aggregates over run_analytics_events.

workspace_id in run_analytics_events is sha256[:16] of the raw UUID,
so all queries hash the incoming workspace_id to match.
"""


def _hash_workspace(workspace_id: str) -> str:
    return hashlib.sha256(workspace_id.encode()).hexdigest()[:16]


def _window_cutoff(days: int) -> datetime:
    return _now() - timedelta(days=days)


# ── Analytics response models ─────────────────────────────────────────────────

class PlaybookStat(BaseModel):
    playbook_slug: str
    run_count: int
    succeeded: int
    failed: int
    success_rate: float
    avg_duration_ms: float | None
    avg_cost_usd: float | None
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    reliability_score: float  # 0–1, same as success_rate for now


class AnalyticsSummary(BaseModel):
    window_days: int
    total_runs: int
    succeeded: int
    failed: int
    success_rate: float
    total_cost_usd: float
    total_input_tokens: int
    total_output_tokens: int
    avg_duration_ms: float | None
    top_playbooks: list[PlaybookStat]


class RunRecord(BaseModel):
    id: str
    run_id: str
    playbook_slug: str
    model: str
    trigger_type: str
    outcome: str
    blocks_executed: int
    tool_calls: int
    input_tokens: int
    output_tokens: int
    duration_ms: int | None
    cost_usd: float | None
    human_verdict: str | None
    created_at: str


# ── Analytics helpers ─────────────────────────────────────────────────────────

def _playbook_stats(db: Session, ws_hash: str, cutoff: datetime) -> list[PlaybookStat]:
    rows = (
        db.query(
            RunAnalyticsEvent.playbook_slug,
            func.count(RunAnalyticsEvent.id).label("run_count"),
            func.sum(
                case((RunAnalyticsEvent.outcome == "succeeded", 1), else_=0)
            ).label("succeeded"),
            func.avg(RunAnalyticsEvent.duration_ms).label("avg_duration_ms"),
            func.avg(RunAnalyticsEvent.cost_usd).label("avg_cost_usd"),
            func.sum(RunAnalyticsEvent.cost_usd).label("total_cost_usd"),
            func.sum(RunAnalyticsEvent.input_tokens).label("total_input"),
            func.sum(RunAnalyticsEvent.output_tokens).label("total_output"),
        )
        .filter(
            RunAnalyticsEvent.workspace_id == ws_hash,
            RunAnalyticsEvent.created_at >= cutoff,
        )
        .group_by(RunAnalyticsEvent.playbook_slug)
        .order_by(func.count(RunAnalyticsEvent.id).desc())
        .all()
    )

    result = []
    for r in rows:
        run_count = r.run_count or 0
        succeeded = int(r.succeeded or 0)
        failed = run_count - succeeded
        success_rate = round(succeeded / run_count, 3) if run_count else 0.0
        result.append(PlaybookStat(
            playbook_slug=r.playbook_slug,
            run_count=run_count,
            succeeded=succeeded,
            failed=failed,
            success_rate=success_rate,
            avg_duration_ms=float(r.avg_duration_ms) if r.avg_duration_ms else None,
            avg_cost_usd=float(r.avg_cost_usd) if r.avg_cost_usd else None,
            total_cost_usd=float(r.total_cost_usd or 0),
            total_input_tokens=int(r.total_input or 0),
            total_output_tokens=int(r.total_output or 0),
            reliability_score=success_rate,
        ))
    return result


# ── Analytics endpoints ───────────────────────────────────────────────────────

@router.get("/analytics/summary", response_model=AnalyticsSummary)
def get_analytics_summary(
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _: str = Depends(require_permission("platform.eval.view")),
    db: Session = Depends(get_db),
    days: int = Query(default=30, ge=1, le=365),
):
    ws_hash = _hash_workspace(workspace_id)
    cutoff = _window_cutoff(days)

    totals = db.query(
        func.count(RunAnalyticsEvent.id).label("total"),
        func.sum(
            case((RunAnalyticsEvent.outcome == "succeeded", 1), else_=0)
        ).label("succeeded"),
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

    return AnalyticsSummary(
        window_days=days,
        total_runs=total,
        succeeded=succeeded,
        failed=failed,
        success_rate=round(succeeded / total, 3) if total else 0.0,
        total_cost_usd=float(totals.total_cost or 0),
        total_input_tokens=int(totals.total_input or 0),
        total_output_tokens=int(totals.total_output or 0),
        avg_duration_ms=float(totals.avg_duration) if totals.avg_duration else None,
        top_playbooks=top,
    )


@router.get("/analytics/playbooks", response_model=list[PlaybookStat])
def get_playbooks(
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _: str = Depends(require_permission("platform.eval.view")),
    db: Session = Depends(get_db),
    days: int = Query(default=30, ge=1, le=365),
):
    ws_hash = _hash_workspace(workspace_id)
    return _playbook_stats(db, ws_hash, _window_cutoff(days))


@router.get("/analytics/runs", response_model=list[RunRecord])
def get_analytics_runs(
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _: str = Depends(require_permission("platform.eval.view")),
    db: Session = Depends(get_db),
    days: int = Query(default=30, ge=1, le=365),
    playbook_slug: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    ws_hash = _hash_workspace(workspace_id)
    q = db.query(RunAnalyticsEvent).filter(
        RunAnalyticsEvent.workspace_id == ws_hash,
        RunAnalyticsEvent.created_at >= _window_cutoff(days),
    )
    if playbook_slug:
        q = q.filter(RunAnalyticsEvent.playbook_slug == playbook_slug)
    if outcome:
        q = q.filter(RunAnalyticsEvent.outcome == outcome)

    rows = q.order_by(RunAnalyticsEvent.created_at.desc()).offset(offset).limit(limit).all()

    return [
        RunRecord(
            id=str(r.id),
            run_id=str(r.run_id),
            playbook_slug=r.playbook_slug,
            model=r.model,
            trigger_type=r.trigger_type,
            outcome=r.outcome,
            blocks_executed=r.blocks_executed,
            tool_calls=r.tool_calls,
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            duration_ms=r.duration_ms,
            cost_usd=float(r.cost_usd) if r.cost_usd is not None else None,
            human_verdict=r.human_verdict,
            created_at=r.created_at.isoformat(),
        )
        for r in rows
    ]


# ── Scorecard response model ──────────────────────────────────────────────────

class PlaybookScorecard(BaseModel):
    playbook_slug: str
    run_count: int
    avg_pct: float
    grade: str
    grade_dist: dict[str, int]
    avg_mechanical: float
    avg_judge: float


def _pct_to_grade(avg_pct: float) -> str:
    if avg_pct >= 90:
        return "A"
    if avg_pct >= 80:
        return "B"
    if avg_pct >= 70:
        return "C"
    if avg_pct >= 60:
        return "D"
    return "F"


@router.get("/analytics/scorecards", response_model=list[PlaybookScorecard])
def get_scorecards(
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _perm: str = Depends(require_permission("platform.eval.view")),
    db: Session = Depends(get_db),
    days: int = Query(default=30, ge=1, le=365),
):
    ws_hash = _hash_workspace(workspace_id)
    cutoff = _window_cutoff(days)

    # Aggregate per slug in a single pass; grade distribution requires individual
    # rows, so fetch all matching score rows joined to the analytics event for
    # workspace filtering, then aggregate in Python.
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

    # Group by slug in Python so we can build grade_dist cheaply.
    buckets: dict[str, list] = defaultdict(list)
    for r in rows:
        buckets[r.slug].append(r)

    result: list[PlaybookScorecard] = []
    for slug, entries in buckets.items():
        run_count = len(entries)
        avg_pct = round(sum(float(e.pct) for e in entries) / run_count, 2)
        grade_dist: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0, "F": 0}
        for e in entries:
            g = e.grade if e.grade in grade_dist else "F"
            grade_dist[g] += 1

        total_mechanical_score = sum(e.mechanical_score for e in entries)
        total_mechanical_max = sum(e.mechanical_max for e in entries)
        avg_mechanical = round(
            total_mechanical_score / total_mechanical_max * 100
            if total_mechanical_max > 0
            else 0.0,
            2,
        )

        judge_entries = [e for e in entries if e.judge_used]
        if judge_entries:
            total_judge_score = sum(e.judge_score for e in judge_entries)
            total_judge_max = sum(e.judge_max for e in judge_entries)
            avg_judge = round(
                total_judge_score / total_judge_max * 100
                if total_judge_max > 0
                else 0.0,
                2,
            )
        else:
            avg_judge = 0.0

        result.append(PlaybookScorecard(
            playbook_slug=slug,
            run_count=run_count,
            avg_pct=avg_pct,
            grade=_pct_to_grade(avg_pct),
            grade_dist=grade_dist,
            avg_mechanical=avg_mechanical,
            avg_judge=avg_judge,
        ))

    # Sort by avg_pct descending so highest-quality playbooks appear first.
    result.sort(key=lambda x: x.avg_pct, reverse=True)
    return result


# ── DORA response model ───────────────────────────────────────────────────────

class DoraStat(BaseModel):
    window_days: int
    total_runs: int
    deployment_frequency: float
    change_failure_rate: float
    avg_duration_ms: float | None
    by_trigger: dict[str, dict]


@router.get("/analytics/dora", response_model=DoraStat)
def get_dora(
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _perm: str = Depends(require_permission("platform.eval.view")),
    db: Session = Depends(get_db),
    days: int = Query(default=30, ge=1, le=365),
):
    ws_hash = _hash_workspace(workspace_id)
    cutoff = _window_cutoff(days)

    # Overall totals.
    totals = (
        db.query(
            func.count(RunAnalyticsEvent.id).label("total"),
            func.sum(
                case((RunAnalyticsEvent.outcome == "succeeded", 1), else_=0)
            ).label("succeeded"),
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
    deployment_frequency = round(succeeded / days, 4)
    change_failure_rate = round(failed / total, 4) if total else 0.0
    avg_duration_ms = float(totals.avg_duration) if totals.avg_duration else None

    # Per-trigger breakdown.
    trigger_rows = (
        db.query(
            RunAnalyticsEvent.trigger_type,
            func.count(RunAnalyticsEvent.id).label("runs"),
            func.sum(
                case((RunAnalyticsEvent.outcome == "succeeded", 1), else_=0)
            ).label("succeeded"),
        )
        .filter(
            RunAnalyticsEvent.workspace_id == ws_hash,
            RunAnalyticsEvent.created_at >= cutoff,
        )
        .group_by(RunAnalyticsEvent.trigger_type)
        .all()
    )

    by_trigger: dict[str, dict] = {}
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

    return DoraStat(
        window_days=days,
        total_runs=total,
        deployment_frequency=deployment_frequency,
        change_failure_rate=change_failure_rate,
        avg_duration_ms=avg_duration_ms,
        by_trigger=by_trigger,
    )


# ══════════════════════════════════════════════════════════════════════════════
# Observability
# ══════════════════════════════════════════════════════════════════════════════

"""
GET  /observability/summary           — workspace health strip
GET  /observability/agents            — per-agent status grid
GET  /observability/stream            — SSE push of summary snapshots every 10 s
GET  /observability/alerts            — paginated watchdog events (last 30 days)
POST /observability/alerts/{id}/resolve — mark a watchdog event resolved
"""

# A running run with no heartbeat update for this long is considered stale
STALE_THRESHOLD_MINUTES = 15


def _stale_cutoff() -> datetime:
    return _now() - timedelta(minutes=STALE_THRESHOLD_MINUTES)


class HealthSummary(BaseModel):
    active_runs: int
    pending_approvals: int
    stale_workers: int
    succeeded_last_24h: int
    failed_last_24h: int
    total_last_24h: int
    error_rate_24h: float


class RecentEvent(BaseModel):
    id: str
    event_type: str
    severity: str
    run_id: str | None
    workflow_id: str | None
    payload: dict
    created_at: str


class ObservabilitySummary(BaseModel):
    health: HealthSummary
    recent_events: list[RecentEvent]


class AgentStatus(BaseModel):
    workflow_id: str
    name: str
    playbook_slug: str | None
    health: str  # healthy | degraded | stale | idle
    active_runs: int
    pending_approvals: int
    stale_runs: int
    success_rate_24h: float
    succeeded_24h: int
    failed_24h: int
    last_run_at: str | None
    last_run_status: str | None


@router.get("/observability/summary", response_model=ObservabilitySummary)
def get_observability_summary(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.runs.view")),
):
    cutoff_24h = _now() - timedelta(hours=24)
    stale_cutoff = _stale_cutoff()

    # All runs in workspace — single-table filter via denormalized workspace_id
    base_q = (
        db.query(Run)
        .filter(Run.workspace_id == workspace_id)
    )

    active_runs = base_q.filter(Run.status == "running").count()
    pending_approvals = base_q.filter(Run.status == "paused").count()

    # Stale: running longer than threshold with no recent heartbeat
    stale_workers = base_q.filter(
        Run.status == "running",
        Run.locked_at < stale_cutoff,
    ).count()

    last_24h = base_q.filter(Run.created_at >= cutoff_24h).all()
    succeeded_24h = sum(1 for r in last_24h if r.status == "succeeded")
    failed_24h = sum(1 for r in last_24h if r.status == "failed")
    total_24h = len(last_24h)
    error_rate = round(failed_24h / total_24h, 3) if total_24h else 0.0

    health = HealthSummary(
        active_runs=active_runs,
        pending_approvals=pending_approvals,
        stale_workers=stale_workers,
        succeeded_last_24h=succeeded_24h,
        failed_last_24h=failed_24h,
        total_last_24h=total_24h,
        error_rate_24h=error_rate,
    )

    events_rows = (
        db.query(WatchdogEvent)
        .filter(WatchdogEvent.workspace_id == workspace_id)
        .order_by(WatchdogEvent.created_at.desc())
        .limit(20)
        .all()
    )
    recent_events = [
        RecentEvent(
            id=str(e.id),
            event_type=e.event_type,
            severity=e.severity,
            run_id=str(e.run_id) if e.run_id else None,
            workflow_id=str(e.workflow_id) if e.workflow_id else None,
            payload=e.payload or {},
            created_at=e.created_at.isoformat(),
        )
        for e in events_rows
    ]

    return ObservabilitySummary(health=health, recent_events=recent_events)


@router.get("/observability/agents", response_model=list[AgentStatus])
def get_agents(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.runs.view")),
):
    cutoff_24h = _now() - timedelta(hours=24)
    stale_cutoff = _stale_cutoff()

    workflows = (
        db.query(Workflow)
        .filter(Workflow.workspace_id == workspace_id)
        .order_by(Workflow.name)
        .all()
    )

    result: list[AgentStatus] = []
    for wf in workflows:
        version_ids_sq = (
            db.query(WorkflowVersion.id)
            .filter(WorkflowVersion.workflow_id == wf.id)
            .subquery()
        )

        runs_24h = (
            db.query(Run)
            .filter(
                Run.workflow_version_id.in_(version_ids_sq),
                Run.created_at >= cutoff_24h,
            )
            .all()
        )

        succeeded_24h = sum(1 for r in runs_24h if r.status == "succeeded")
        failed_24h = sum(1 for r in runs_24h if r.status == "failed")
        total_24h = len(runs_24h)
        success_rate = round(succeeded_24h / total_24h, 3) if total_24h else 0.0

        active = sum(1 for r in runs_24h if r.status == "running")
        pending = sum(1 for r in runs_24h if r.status == "paused")

        # Stale: running with locked_at older than threshold
        stale = (
            db.query(func.count(Run.id))
            .filter(
                Run.workflow_version_id.in_(version_ids_sq),
                Run.status == "running",
                Run.locked_at < stale_cutoff,
            )
            .scalar()
        ) or 0

        last_run = (
            db.query(Run)
            .filter(Run.workflow_version_id.in_(version_ids_sq))
            .order_by(Run.created_at.desc())
            .first()
        )

        # Health classification
        if stale > 0:
            health = "stale"
        elif total_24h == 0:
            health = "idle"
        elif success_rate < 0.8 or (last_run and last_run.status == "failed"):
            health = "degraded"
        else:
            health = "healthy"

        result.append(AgentStatus(
            workflow_id=str(wf.id),
            name=wf.name,
            playbook_slug=wf.playbook_slug,
            health=health,
            active_runs=active,
            pending_approvals=pending,
            stale_runs=stale,
            success_rate_24h=success_rate,
            succeeded_24h=succeeded_24h,
            failed_24h=failed_24h,
            last_run_at=last_run.created_at.isoformat() if last_run else None,
            last_run_status=last_run.status if last_run else None,
        ))

    return result


# ── SSE live stream ───────────────────────────────────────────────────────────

def _build_summary_payload(workspace_id: str) -> str:
    """Build a fresh summary snapshot using a short-lived DB session."""
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        cutoff_24h = now - timedelta(hours=24)
        stale_cutoff = now - timedelta(minutes=STALE_THRESHOLD_MINUTES)

        base_q = (
            db.query(Run)
            .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
            .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
            .filter(Workflow.workspace_id == workspace_id)
        )

        active_runs = base_q.filter(Run.status == "running").count()
        pending_approvals = base_q.filter(Run.status == "paused").count()
        stale_workers = base_q.filter(Run.status == "running", Run.locked_at < stale_cutoff).count()

        last_24h = base_q.filter(Run.created_at >= cutoff_24h).all()
        succeeded_24h = sum(1 for r in last_24h if r.status == "succeeded")
        failed_24h = sum(1 for r in last_24h if r.status == "failed")
        total_24h = len(last_24h)

        events_rows = (
            db.query(WatchdogEvent)
            .filter(WatchdogEvent.workspace_id == workspace_id)
            .order_by(WatchdogEvent.created_at.desc())
            .limit(20)
            .all()
        )

        # ── Per-run detail: active runs ────────────────────────────────────────
        active_run_rows = (
            db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"))
            .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
            .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
            .filter(
                Workflow.workspace_id == workspace_id,
                Run.status == "running",
            )
            .order_by(Run.started_at.asc())
            .limit(20)
            .all()
        )

        active_runs_detail = []
        for run, wf_id, wf_name in active_run_rows:
            elapsed = int((now - run.started_at).total_seconds()) if run.started_at else None
            heartbeat_ref = run.last_heartbeat_time or run.locked_at
            silent_for = int((now - heartbeat_ref).total_seconds()) if heartbeat_ref else None
            active_runs_detail.append({
                "run_id": str(run.id),
                "workflow_id": str(wf_id),
                "workflow_name": wf_name,
                "current_block": run.current_block_id,
                "elapsed_seconds": elapsed,
                "last_heartbeat_cursor": heartbeat_ref.isoformat() if heartbeat_ref else None,
                "silent_for_seconds": silent_for,
            })

        # ── Per-run detail: waiting for user (paused / approval gate) ─────────
        paused_run_rows = (
            db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"))
            .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
            .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
            .filter(
                Workflow.workspace_id == workspace_id,
                Run.status == "paused",
            )
            .order_by(Run.paused_at.asc())
            .limit(20)
            .all()
        )

        waiting_for_user = []
        for run, wf_id, wf_name in paused_run_rows:
            waiting_since = run.paused_at or run.started_at
            waiting_seconds = int((now - waiting_since).total_seconds()) if waiting_since else None
            waiting_for_user.append({
                "run_id": str(run.id),
                "workflow_id": str(wf_id),
                "workflow_name": wf_name,
                "gate_id": run.current_block_id,
                "waiting_since": waiting_since.isoformat() if waiting_since else None,
                "waiting_seconds": waiting_seconds,
            })

        # ── Per-run detail: stale workers ─────────────────────────────────────
        stale_run_rows = (
            db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"))
            .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
            .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
            .filter(
                Workflow.workspace_id == workspace_id,
                Run.status == "running",
                Run.locked_at < stale_cutoff,
            )
            .order_by(Run.locked_at.asc())
            .limit(20)
            .all()
        )

        stale_workers_detail = []
        for run, wf_id, wf_name in stale_run_rows:
            heartbeat_ref = run.last_heartbeat_time or run.locked_at
            silent_for = int((now - heartbeat_ref).total_seconds()) if heartbeat_ref else None
            stale_workers_detail.append({
                "run_id": str(run.id),
                "workflow_id": str(wf_id),
                "workflow_name": wf_name,
                "last_heartbeat_cursor": heartbeat_ref.isoformat() if heartbeat_ref else None,
                "silent_for_seconds": silent_for,
                "locked_by": run.locked_by,
            })

        payload = {
            "health": {
                "active_runs": active_runs,
                "pending_approvals": pending_approvals,
                "stale_workers": stale_workers,
                "succeeded_last_24h": succeeded_24h,
                "failed_last_24h": failed_24h,
                "total_last_24h": total_24h,
                "error_rate_24h": round(failed_24h / total_24h, 3) if total_24h else 0.0,
            },
            "recent_events": [
                {
                    "id": str(e.id),
                    "event_type": e.event_type,
                    "severity": e.severity,
                    "run_id": str(e.run_id) if e.run_id else None,
                    "workflow_id": str(e.workflow_id) if e.workflow_id else None,
                    "payload": e.payload or {},
                    "created_at": e.created_at.isoformat(),
                }
                for e in events_rows
            ],
            "active_runs_detail": active_runs_detail,
            "waiting_for_user": waiting_for_user,
            "stale_workers_detail": stale_workers_detail,
        }
        return json.dumps(payload)
    finally:
        db.close()


@router.get("/observability/stream")
async def stream_summary(
    request: Request,
    workspace_id: str = Depends(get_workspace_id_sse),
    _role: str = Depends(require_workspace_role_sse("admin", "developer", "security", "viewer")),
):
    """SSE endpoint — pushes a fresh summary snapshot every 10 seconds."""
    PUSH_INTERVAL = 10  # seconds
    MAX_DURATION  = 300  # reconnect after 5 min to avoid stale connections

    async def event_generator():
        deadline = asyncio.get_event_loop().time() + MAX_DURATION
        while asyncio.get_event_loop().time() < deadline:
            if await request.is_disconnected():
                break
            try:
                payload = await asyncio.get_event_loop().run_in_executor(
                    None, _build_summary_payload, workspace_id
                )
                yield f"data: {payload}\n\n"
            except Exception:
                yield "data: {\"error\": true}\n\n"
            await asyncio.sleep(PUSH_INTERVAL)
        yield "data: {\"kind\": \"stream_timeout\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Alerts endpoints ──────────────────────────────────────────────────────────

class AlertResponse(BaseModel):
    id: str
    event_type: str
    severity: str
    run_id: str | None
    workflow_id: str | None
    payload: dict
    created_at: str
    resolved_at: str | None


@router.get("/observability/alerts", response_model=list[AlertResponse])
def list_alerts(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.runs.view")),
    event_type: str | None = Query(default=None, description="Filter by event_type"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Paginated watchdog events for the workspace, last 30 days."""
    cutoff_30d = _now() - timedelta(days=30)

    q = (
        db.query(WatchdogEvent)
        .filter(
            WatchdogEvent.workspace_id == workspace_id,
            WatchdogEvent.created_at >= cutoff_30d,
        )
    )
    if event_type:
        q = q.filter(WatchdogEvent.event_type == event_type)

    rows = (
        q.order_by(WatchdogEvent.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [
        AlertResponse(
            id=str(e.id),
            event_type=e.event_type,
            severity=e.severity,
            run_id=str(e.run_id) if e.run_id else None,
            workflow_id=str(e.workflow_id) if e.workflow_id else None,
            payload=e.payload or {},
            created_at=e.created_at.isoformat(),
            resolved_at=e.resolved_at.isoformat() if e.resolved_at else None,
        )
        for e in rows
    ]


@router.post("/observability/alerts/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.run")),
):
    """Mark a watchdog event as resolved by setting resolved_at to now."""
    event = (
        db.query(WatchdogEvent)
        .filter(
            WatchdogEvent.id == alert_id,
            WatchdogEvent.workspace_id == workspace_id,
        )
        .first()
    )
    if not event:
        raise HTTPException(status_code=404, detail="Alert not found")

    event.resolved_at = _now()
    db.commit()
    db.refresh(event)

    return AlertResponse(
        id=str(event.id),
        event_type=event.event_type,
        severity=event.severity,
        run_id=str(event.run_id) if event.run_id else None,
        workflow_id=str(event.workflow_id) if event.workflow_id else None,
        payload=event.payload or {},
        created_at=event.created_at.isoformat(),
        resolved_at=event.resolved_at.isoformat() if event.resolved_at else None,
    )
