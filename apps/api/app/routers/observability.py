"""
GET  /observability/summary           — workspace health strip
GET  /observability/agents            — per-agent status grid
GET  /observability/stream            — SSE push of summary snapshots every 10 s
GET  /observability/alerts            — paginated watchdog events (last 30 days)
POST /observability/alerts/{id}/resolve — mark a watchdog event resolved
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_workspace_role
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.models.run import Run
from app.models.watchdog_event import WatchdogEvent
from app.routers.runs import get_workspace_id_sse, require_workspace_role_sse
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


@router.get("/stream")
async def stream_summary(
    request: Request,
    workspace_id: str = Depends(get_workspace_id_sse),
    _role: str = Depends(require_workspace_role_sse("admin", "editor", "viewer")),
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


@router.get("/alerts", response_model=list[AlertResponse])
def list_alerts(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
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


@router.post("/alerts/{alert_id}/resolve", response_model=AlertResponse)
def resolve_alert(
    alert_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor")),
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
