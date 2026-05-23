"""
GET /dashboard  — outcome-based summary for the workspace
"""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_workspace_role
from app.core.database import get_db
from app.models.run import Run
from app.models.workflow import Workflow, WorkflowVersion

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


class WeekStats(BaseModel):
    issues_picked_up: int
    prs_opened: int
    total_runs: int
    succeeded_runs: int
    failed_runs: int
    success_rate: float  # 0–100


class RecentRun(BaseModel):
    run_id: str
    workflow_id: str
    workflow_name: str
    status: str
    issue_number: int | None
    issue_title: str | None
    pr_url: str | None
    started_at: str | None
    created_at: str


class AgentStatus(BaseModel):
    workflow_id: str
    name: str
    last_run_status: str | None
    last_run_at: str | None


class DashboardOut(BaseModel):
    week: WeekStats
    recent_runs: list[RecentRun]
    agents: list[AgentStatus]


@router.get("", response_model=DashboardOut)
def get_dashboard(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    # All workflow version IDs for this workspace
    version_ids_sq = (
        db.query(WorkflowVersion.id)
        .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .filter(Workflow.workspace_id == workspace_id)
        .subquery()
    )

    # ── This-week stats ──────────────────────────────────────────────────────
    week_start = datetime.now(timezone.utc) - timedelta(days=7)
    week_runs = (
        db.query(Run)
        .filter(
            Run.workflow_version_id.in_(version_ids_sq),
            Run.created_at >= week_start,
        )
        .all()
    )

    issues_picked_up = sum(
        1 for r in week_runs
        if (r.state or {}).get("_trigger", {}).get("issue_number")
    )
    prs_opened = sum(
        1 for r in week_runs
        if (r.state or {}).get("pr_url")
    )
    succeeded = sum(1 for r in week_runs if r.status == "succeeded")
    failed = sum(1 for r in week_runs if r.status == "failed")
    total = len(week_runs)
    success_rate = round((succeeded / total) * 100, 1) if total else 0.0

    week_stats = WeekStats(
        issues_picked_up=issues_picked_up,
        prs_opened=prs_opened,
        total_runs=total,
        succeeded_runs=succeeded,
        failed_runs=failed,
        success_rate=success_rate,
    )

    # ── Recent runs (last 10) ────────────────────────────────────────────────
    recent = (
        db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"))
        .join(WorkflowVersion, WorkflowVersion.id == Run.workflow_version_id)
        .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
        .filter(
            Run.workflow_version_id.in_(version_ids_sq),
            Workflow.workspace_id == workspace_id,
        )
        .order_by(Run.created_at.desc())
        .limit(10)
        .all()
    )

    recent_runs = []
    for run, wf_id, wf_name in recent:
        state = run.state or {}
        trigger = state.get("_trigger") or state.get("github_issue") or {}
        recent_runs.append(RecentRun(
            run_id=str(run.id),
            workflow_id=str(wf_id),
            workflow_name=wf_name,
            status=run.status,
            issue_number=trigger.get("issue_number"),
            issue_title=trigger.get("title") or trigger.get("issue_title"),
            pr_url=state.get("pr_url"),
            started_at=run.started_at.isoformat() if run.started_at else None,
            created_at=run.created_at.isoformat(),
        ))

    # ── Agent statuses ───────────────────────────────────────────────────────
    workflows = (
        db.query(Workflow)
        .filter(Workflow.workspace_id == workspace_id)
        .order_by(Workflow.updated_at.desc())
        .all()
    )

    agents = []
    for wf in workflows:
        last_run = (
            db.query(Run)
            .join(WorkflowVersion, WorkflowVersion.id == Run.workflow_version_id)
            .filter(WorkflowVersion.workflow_id == wf.id)
            .order_by(Run.created_at.desc())
            .first()
        )
        agents.append(AgentStatus(
            workflow_id=str(wf.id),
            name=wf.name,
            last_run_status=last_run.status if last_run else None,
            last_run_at=last_run.created_at.isoformat() if last_run else None,
        ))

    return DashboardOut(week=week_stats, recent_runs=recent_runs, agents=agents)
