"""Workspace-wide runs router: ``GET /runs`` and ``GET /runs/{run_id}`` (split from runs.py).
"""
from datetime import datetime, timezone
from uuid import UUID
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.auth import get_workspace_id, get_user_id, require_permission, DEV_USER_ID
from app.core.database import get_db
from app.models.run import Run
from app.models.workflow import Workflow, WorkflowVersion
from app.models.project import Project
from app.schemas.run import RunWithWorkflowOut

log = structlog.get_logger("app.routers.runs")


# ── Workspace-wide runs router ────────────────────────────────────────────────

workspace_runs_router = APIRouter(prefix="/runs", tags=["runs"])


# ── Workspace-wide run endpoints ──────────────────────────────────────────────

@workspace_runs_router.get("", response_model=list[RunWithWorkflowOut])
def list_all_runs(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _: str = Depends(require_permission("platform.runs.view")),
    status: str | None = None,
    project_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    repository: str | None = None,
    workflow_name: str | None = None,
    created_after: float | None = None,
):
    """All runs across all agents in the workspace, newest first.
    
    Filters:
    - status: pending/running/paused/succeeded/failed/cancelled
    - project_id: filter by project
    - repository: filter by repository (e.g., "owner/repo")
    - workflow_name: filter by workflow/playbook name
    - created_after: filter by creation timestamp (unix seconds or ISO datetime)
    """
    from sqlalchemy import text as _text
    effective_workspace_id = workspace_id
    if project_id and user_id != DEV_USER_ID:
        proj = db.query(Project).filter(Project.id == project_id).first()
        if proj and str(proj.workspace_id) != workspace_id:
            proj_ws = str(proj.workspace_id)
            member = db.execute(
                _text("SELECT 1 FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid"),
                {"ws": proj_ws, "uid": user_id},
            ).fetchone()
            if member:
                effective_workspace_id = proj_ws

    q = (
        db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"),
                 Workflow.project_id.label("proj_id"), Project.name.label("proj_name"))
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, WorkflowVersion.workflow_id == Workflow.id)
        .outerjoin(Project, Workflow.project_id == Project.id)
        .filter(Workflow.workspace_id == effective_workspace_id)
        .order_by(Run.created_at.desc())
    )
    if status:
        q = q.filter(Run.status == status)
    if project_id:
        q = q.filter(Workflow.project_id == project_id)
    if workflow_name:
        q = q.filter(Workflow.name == workflow_name)
    if created_after is not None:
        try:
            # Try ISO datetime string first (e.g., "2026-05-28T12:34:56Z")
            if isinstance(created_after, str):
                after_dt = datetime.fromisoformat(created_after.replace('Z', '+00:00'))
            else:
                # Try Unix timestamp
                after_dt = datetime.fromtimestamp(created_after, tz=timezone.utc)
        except (ValueError, TypeError, OSError):
            # Fall back to no filter if parsing fails
            after_dt = None
        if after_dt:
            q = q.filter(Run.created_at >= after_dt)
    
    # Filter by repository - requires checking the state JSON
    # Only include runs where repo matches (extracted from _trigger.repository.full_name)
    if repository:
        q = q.filter(
            Run.state["_trigger"]["repository"]["full_name"].astext == repository
        )
    
    results = []
    for run, wf_id, wf_name, proj_id, proj_name in q.offset(offset).limit(limit).all():
        out = RunWithWorkflowOut(
            id=run.id,
            workflow_version_id=run.workflow_version_id,
            triggered_by=run.triggered_by,
            status=run.status,
            started_at=run.started_at,
            paused_at=run.paused_at,
            completed_at=run.completed_at,
            current_block_id=run.current_block_id,
            created_at=run.created_at,
            workflow_id=str(wf_id),
            workflow_name=wf_name,
            project_id=str(proj_id) if proj_id else None,
            project_name=proj_name,
            state=run.state,
        )
        results.append(out)
    return results


@workspace_runs_router.get("/{run_id}", response_model=RunWithWorkflowOut)
def get_workspace_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.runs.view")),
):
    """Single run by ID, scoped to workspace, with workflow name."""
    row = (
        db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"),
                 Workflow.project_id.label("proj_id"), Project.name.label("proj_name"))
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, WorkflowVersion.workflow_id == Workflow.id)
        .outerjoin(Project, Workflow.project_id == Project.id)
        .filter(Workflow.workspace_id == workspace_id, Run.id == run_id)
        .first()
    )
    if not row:
        log.warning("run.not_found", run_id=str(run_id), workspace_id=workspace_id)
        raise HTTPException(status_code=404, detail="Run not found")
    run, wf_id, wf_name, proj_id, proj_name = row
    return RunWithWorkflowOut(
        id=run.id,
        workflow_version_id=run.workflow_version_id,
        triggered_by=run.triggered_by,
        status=run.status,
        started_at=run.started_at,
        paused_at=run.paused_at,
        completed_at=run.completed_at,
        current_block_id=run.current_block_id,
        created_at=run.created_at,
        workflow_id=str(wf_id),
        workflow_name=wf_name,
        project_id=str(proj_id) if proj_id else None,
        project_name=proj_name,
        state=run.state,
        outcome=run.outcome,
    )
