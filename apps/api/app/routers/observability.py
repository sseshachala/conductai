"""
GET /observability/summary  — workspace health strip (active runs, stale workers, approvals, error rate)
GET /observability/agents   — per-agent status grid
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_workspace_role
from app.core.database import get_db
from app.models.run import Run
from app.models.watchdog_event import WatchdogEvent
from app.models.workflow import Workflow, WorkflowVersion

router = APIRouter(prefix="/observability", tags=["observability"])

# A running run with no heartbeat update for this long is considered stale
STALE_THRESHOLD_MINUTES = 15


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


@router.get("/summary", response_model=ObservabilitySummary)
def get_summary(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    cutoff_24h = _now() - timedelta(hours=24)
    stale_cutoff = _stale_cutoff()

    # All runs in workspace joined to workflow
    base_q = (
        db.query(Run)
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .filter(Workflow.workspace_id == workspace_id)
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


@router.get("/agents", response_model=list[AgentStatus])
def get_agents(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
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
