"""
Analytics API — aggregates over run_analytics_events.

workspace_id in run_analytics_events is sha256[:16] of the raw UUID,
so all queries hash the incoming workspace_id to match.

Endpoints:
  GET /analytics/summary    — workspace totals for a time window
  GET /analytics/playbooks  — per-playbook rollup (success rate, cost, duration)
  GET /analytics/runs       — paginated raw run records
"""
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_permission
from app.core.database import get_db
from app.models.run_analytics_event import RunAnalyticsEvent
from app.models.run_online_score import RunOnlineScore

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_workspace(workspace_id: str) -> str:
    return hashlib.sha256(workspace_id.encode()).hexdigest()[:16]


def _window_cutoff(days: int) -> datetime:
    return _now() - timedelta(days=days)


# ── Response models ───────────────────────────────────────────────────────────

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


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/summary", response_model=AnalyticsSummary)
def get_summary(
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


@router.get("/playbooks", response_model=list[PlaybookStat])
def get_playbooks(
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _: str = Depends(require_permission("platform.eval.view")),
    db: Session = Depends(get_db),
    days: int = Query(default=30, ge=1, le=365),
):
    ws_hash = _hash_workspace(workspace_id)
    return _playbook_stats(db, ws_hash, _window_cutoff(days))


@router.get("/runs", response_model=list[RunRecord])
def get_runs(
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


@router.get("/scorecards", response_model=list[PlaybookScorecard])
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
    from collections import defaultdict

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


@router.get("/dora", response_model=DoraStat)
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
