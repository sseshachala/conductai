"""
GET /dashboard  — outcome-based summary for the workspace
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, case
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_workspace_role
from app.core.database import get_db
from app.models.run import Run
from app.models.workflow import Workflow, WorkflowVersion

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

REVIEW_SLUGS   = {"pr_reviewer", "copilot_reviewer", "security_scanner"}
INCIDENT_SLUGS = {"incident_responder", "postmortem_drafter"}
TRIAGE_SLUGS   = {"issue_triage"}


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
    success_rate: float   # 0–100
    last_run_status: str | None
    last_run_at: str | None


class AttentionRun(BaseModel):
    run_id: str
    workflow_id: str
    workflow_name: str
    status: str
    triggered_by: str | None
    created_at: str


class RecentRun(BaseModel):
    run_id: str
    workflow_id: str
    workflow_name: str
    status: str
    triggered_by: str | None
    started_at: str | None
    created_at: str


class DashboardOut(BaseModel):
    outcomes: OutcomeStats
    needs_attention: list[AttentionRun]
    agent_health: list[AgentHealth]
    recent_activity: list[RecentRun]


@router.get("", response_model=DashboardOut)
def get_dashboard(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    week_start = datetime.now(timezone.utc) - timedelta(days=7)

    # ── Week runs joined with Workflow for playbook_slug ─────────────────────
    week_rows = (
        db.query(Run, Workflow.playbook_slug.label("slug"))
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .filter(Workflow.workspace_id == workspace_id, Run.created_at >= week_start)
        .all()
    )

    prs_opened = sum(1 for r, _ in week_rows if (r.state or {}).get("pr_url"))
    issues_triaged = sum(
        1 for r, slug in week_rows
        if slug in TRIAGE_SLUGS and r.status == "succeeded"
    )
    reviews_completed = sum(
        1 for r, slug in week_rows
        if slug in REVIEW_SLUGS and r.status == "succeeded"
    )
    incidents_investigated = sum(
        1 for r, slug in week_rows
        if slug in INCIDENT_SLUGS and r.status == "succeeded"
    )
    successful_automations = sum(1 for r, _ in week_rows if r.status == "succeeded")
    failed_automations = sum(1 for r, _ in week_rows if r.status == "failed")

    outcomes = OutcomeStats(
        prs_opened=prs_opened,
        issues_triaged=issues_triaged,
        reviews_completed=reviews_completed,
        incidents_investigated=incidents_investigated,
        successful_automations=successful_automations,
        failed_automations=failed_automations,
    )

    # ── Needs Attention — failed/paused runs, most recent first ──────────────
    attention_rows = (
        db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"))
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .filter(
            Workflow.workspace_id == workspace_id,
            Run.status.in_(["failed", "paused"]),
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
            created_at=run.created_at.isoformat(),
        )
        for run, wf_id, wf_name in attention_rows
    ]

    # ── Agent Health — all-time per-workflow aggregation ─────────────────────
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

    # Last run status per workflow — one query via max(created_at) join
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
        )
        for run, wf_id, wf_name in recent_rows
    ]

    return DashboardOut(
        outcomes=outcomes,
        needs_attention=needs_attention,
        agent_health=agent_health,
        recent_activity=recent_activity,
    )
