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
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_workspace_role
from app.core.database import get_db
from app.models.run_analytics_event import RunAnalyticsEvent

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
                func.cast(RunAnalyticsEvent.outcome == "succeeded", text("int"))
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
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
    db: Session = Depends(get_db),
    days: int = Query(default=30, ge=1, le=365),
):
    ws_hash = _hash_workspace(workspace_id)
    cutoff = _window_cutoff(days)

    totals = db.query(
        func.count(RunAnalyticsEvent.id).label("total"),
        func.sum(
            func.cast(RunAnalyticsEvent.outcome == "succeeded", text("int"))
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
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
    db: Session = Depends(get_db),
    days: int = Query(default=30, ge=1, le=365),
):
    ws_hash = _hash_workspace(workspace_id)
    return _playbook_stats(db, ws_hash, _window_cutoff(days))


@router.get("/runs", response_model=list[RunRecord])
def get_runs(
    workspace_id: Annotated[str, Depends(get_workspace_id)],
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
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
