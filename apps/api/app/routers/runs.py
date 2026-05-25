import json
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import redis
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session


def _now() -> datetime:
    return datetime.now(timezone.utc)

from app.core.auth import get_workspace_id, require_workspace_role, _verify_clerk_token, _clerk_enabled, DEV_WORKSPACE_ID, DEV_USER_ID
from app.core.config import settings
from app.core.database import get_db
from app.models.run import Run, RunEvent
from app.models.workflow import Workflow, WorkflowVersion
from app.schemas.run import RunCreate, RunDetailOut, RunOut, RunWithWorkflowOut

router = APIRouter(prefix="/workflows/{workflow_id}/runs", tags=["runs"])

# ── Workspace-wide runs router ────────────────────────────────────────────────

workspace_runs_router = APIRouter(prefix="/runs", tags=["runs"])

QUEUE_KEY = "marshal:runs:queue"


def get_workspace_id_sse(
    request: Request,
    workspace_id: str | None = Depends(lambda: None),
) -> str:
    """Auth dependency for SSE endpoints — accepts token via Authorization header.
    EventSource cannot set custom headers so workspace_id comes from x-workspace-id header."""
    auth_header = request.headers.get("Authorization", "")
    x_ws = request.headers.get("x-workspace-id")

    if not _clerk_enabled():
        return x_ws or DEV_WORKSPACE_ID

    # CLI API key — header only (query params are logged by proxies)
    api_key_hdr = request.headers.get("x-api-key")
    from app.core.config import settings as _settings
    cli_key = _settings.cli_api_key
    if cli_key and api_key_hdr == cli_key:
        if not _settings.cli_workspace_id:
            raise HTTPException(status_code=500, detail="CLI_WORKSPACE_ID is not configured on the server")
        return _settings.cli_workspace_id

    raw_token = None
    if auth_header.startswith("Bearer "):
        raw_token = auth_header.removeprefix("Bearer ")

    if not raw_token:
        raise HTTPException(status_code=401, detail="Authorization required")

    claims = _verify_clerk_token(raw_token)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    ws = x_ws or claims.get("org_id") or claims.get("sub")
    if not ws:
        raise HTTPException(status_code=401, detail="No workspace in token claims")
    return ws


def _get_user_id_from_request(request: Request) -> str:
    """Extract Clerk user_id from the Authorization header for SSE endpoints."""
    if not _clerk_enabled():
        return DEV_USER_ID
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization required")
    claims = _verify_clerk_token(auth_header.removeprefix("Bearer "))
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="No user ID in token")
    return user_id


def get_user_workspace_role_sse(
    request: Request,
    workspace_id: str = Depends(get_workspace_id_sse),
    db: Session = Depends(get_db),
) -> str:
    """Role-checking dependency for SSE endpoints (mirrors get_user_workspace_role)."""
    if not _clerk_enabled():
        return "admin"

    user_id = _get_user_id_from_request(request)

    from sqlalchemy import text
    row = db.execute(
        text("SELECT role FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid"),
        {"ws": workspace_id, "uid": user_id},
    ).fetchone()
    if not row:
        owner_row = db.execute(
            text("SELECT owner_id FROM workspaces WHERE id = :ws AND owner_id = :uid"),
            {"ws": workspace_id, "uid": user_id},
        ).fetchone()
        if not owner_row:
            raise HTTPException(status_code=403, detail="Not a member of this workspace")
        return "admin"
    return row.role


def require_workspace_role_sse(*allowed_roles: str):
    """Role-gating factory for SSE endpoints (mirrors require_workspace_role)."""
    def _check(role: str = Depends(get_user_workspace_role_sse)) -> str:
        if role not in allowed_roles:
            raise HTTPException(status_code=403, detail=f"Requires role: {', '.join(allowed_roles)}")
        return role
    return _check


def _redis():
    return redis.from_url(settings.redis_url, decode_responses=True)


def _get_workflow(workflow_id: UUID, workspace_id: str, db: Session) -> Workflow:
    """Fetch workflow and verify it belongs to the caller's workspace."""
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


def _get_run(run_id: UUID, workflow_id: UUID, db: Session) -> Run:
    """Fetch run and verify it belongs to the given workflow (prevents cross-tenant access)."""
    version_ids = db.query(WorkflowVersion.id).filter(
        WorkflowVersion.workflow_id == workflow_id
    ).subquery()
    run = db.query(Run).filter(
        Run.id == run_id,
        Run.workflow_version_id.in_(version_ids),
    ).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("", response_model=list[RunOut])
def list_runs(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    _get_workflow(workflow_id, workspace_id, db)
    # Return runs across ALL versions so autosave version bumps don't hide history
    version_ids = db.query(WorkflowVersion.id).filter(
        WorkflowVersion.workflow_id == workflow_id
    ).subquery()
    return (
        db.query(Run)
        .filter(Run.workflow_version_id.in_(version_ids))
        .order_by(Run.created_at.desc())
        .all()
    )


@router.post("", response_model=RunOut, status_code=201)
def create_run(
    workflow_id: UUID,
    body: RunCreate,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor")),
):
    workflow = _get_workflow(workflow_id, workspace_id, db)
    if not workflow.current_version_id:
        raise HTTPException(status_code=400, detail="Workflow has no published version")

    initial_state = body.initial_state or {}
    if body.dry_run:
        initial_state["__dry_run"] = True

    # If the caller didn't provide an explicit turn budget, estimate it server-side
    # so CLI and API callers get the same guard as the canvas preflight banner.
    max_turns = body.max_turns
    if not max_turns:
        from app.routers.workflows import _estimate_turns_for_graph
        issue = (
            initial_state.get("github_issue")
            or initial_state.get("_trigger", {}).get("issue")
            or initial_state.get("_trigger", {}).get("pull_request")
            or {}
        )
        try:
            graph = workflow.current_version.graph or {} if workflow.current_version else {}
            pf = _estimate_turns_for_graph(
                graph,
                issue.get("title", ""),
                issue.get("body", ""),
            )
            max_turns = pf["suggested_max_turns"]
        except Exception:
            max_turns = 20

    initial_state["__max_turns"] = max_turns
    run = Run(
        workflow_version_id=workflow.current_version_id,
        triggered_by=body.triggered_by,
        status="pending",
        state=initial_state,
        max_turns=max_turns,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    _redis().rpush(QUEUE_KEY, str(run.id))

    return run


@router.get("/{run_id}", response_model=RunDetailOut)
def get_run(
    workflow_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    # Verify workflow belongs to this workspace, then scope run to that workflow.
    _get_workflow(workflow_id, workspace_id, db)
    run = (
        db.query(Run)
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .filter(Run.id == run_id, WorkflowVersion.workflow_id == workflow_id)
        .first()
    )
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


_RUN_CHANNEL_PREFIX = "marshal:run:"
_SSE_TIMEOUT_SECONDS = 300  # close stream after 5 min of silence; client reconnects


def publish_run_event(run_id: str) -> None:
    """Notify SSE subscribers that a new event is available for this run."""
    try:
        _redis().publish(f"{_RUN_CHANNEL_PREFIX}{run_id}", "1")
    except Exception:
        pass


@router.get("/{run_id}/stream")
def stream_run_events(
    workflow_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id_sse),
    _role: str = Depends(require_workspace_role_sse("admin", "editor", "viewer")),
):
    """SSE stream of run_events driven by Redis pub/sub — one DB query per notification."""
    _get_workflow(workflow_id, workspace_id, db)
    run = _get_run(run_id, workflow_id, db)

    def event_generator():
        from app.core.database import SessionLocal

        seen_ids: set = set()
        stream_db = SessionLocal()
        pubsub = _redis().pubsub()
        pubsub.subscribe(f"{_RUN_CHANNEL_PREFIX}{str(run_id)}")

        def flush_new_events():
            events = (
                stream_db.query(RunEvent)
                .filter(RunEvent.run_id == run_id)
                .order_by(RunEvent.created_at)
                .all()
            )
            for ev in events:
                if ev.id not in seen_ids:
                    seen_ids.add(ev.id)
                    yield f"data: {json.dumps({'id': str(ev.id), 'kind': ev.kind, 'block_id': ev.block_id, 'payload': ev.payload})}\n\n"

        def is_terminal() -> str | None:
            stream_db.expire_all()
            current = stream_db.query(Run).filter(Run.id == run_id).first()
            return current.status if current and current.status in ("succeeded", "failed", "paused", "cancelled") else None

        try:
            # Flush any events already written before we subscribed
            yield from flush_new_events()
            terminal = is_terminal()
            if terminal:
                if terminal == "paused":
                    r = stream_db.query(Run).filter(Run.id == run_id).first()
                    yield f"data: {json.dumps({'kind': 'run_paused', 'block_id': r.current_block_id if r else None, 'payload': {}})}\n\n"
                yield "data: [DONE]\n\n"
                return

            # Wait for notifications; timeout closes the stream so the client reconnects
            for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                yield from flush_new_events()
                terminal = is_terminal()
                if terminal:
                    if terminal == "paused":
                        r = stream_db.query(Run).filter(Run.id == run_id).first()
                        yield f"data: {json.dumps({'kind': 'run_paused', 'block_id': r.current_block_id if r else None, 'payload': {}})}\n\n"
                    yield "data: [DONE]\n\n"
                    break
        finally:
            pubsub.unsubscribe()
            pubsub.close()
            stream_db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Approval endpoints ────────────────────────────────────────────────────────

class ApprovalDecision(BaseModel):
    decision: str  # "approved" or "rejected"
    approver: str | None = None


@router.post("/{run_id}/cancel")
def cancel_run(
    workflow_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor")),
):
    """Mark a running or pending run as cancelled. The worker will abort on next check."""
    _get_workflow(workflow_id, workspace_id, db)
    run = _get_run(run_id, workflow_id, db)
    if run.status not in ("running", "pending"):
        raise HTTPException(status_code=400, detail=f"Run cannot be cancelled (status: {run.status})")
    run.status = "cancelled"
    run.finished_at = _now()
    db.add(RunEvent(run_id=run_id, block_id=None, kind="run_cancelled", payload={"reason": "user_cancelled"}))
    db.commit()
    return {"run_id": str(run_id), "status": "cancelled"}


@router.post("/{run_id}/approve")
def approve_run(
    workflow_id: UUID,
    run_id: UUID,
    body: ApprovalDecision,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor")),
):
    """
    Called by the human approver (or Slack webhook) to resume a paused run.
    Stores the decision in run.state and re-queues the run.
    """
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="decision must be 'approved' or 'rejected'")

    _get_workflow(workflow_id, workspace_id, db)
    run = _get_run(run_id, workflow_id, db)
    if run.status != "paused":
        raise HTTPException(status_code=400, detail=f"Run is not paused (status: {run.status})")

    block_id = run.current_block_id
    if not block_id:
        raise HTTPException(status_code=400, detail="No approval block recorded on paused run")

    state = dict(run.state or {})
    state[f"__approval_{block_id}"] = body.decision
    if body.approver:
        state[f"__approver_{block_id}"] = body.approver
    run.state = state
    run.status = "pending"
    run.paused_at = None
    db.commit()

    event = RunEvent(
        run_id=run_id,
        block_id=block_id,
        kind="approval_received",
        payload={"decision": body.decision, "approver": body.approver},
    )
    db.add(event)
    db.commit()

    _redis().rpush(QUEUE_KEY, str(run_id))

    return {"run_id": str(run_id), "decision": body.decision, "status": "queued"}


# ── Workspace-wide run endpoints ──────────────────────────────────────────────

@workspace_runs_router.get("", response_model=list[RunWithWorkflowOut])
def list_all_runs(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """All runs across all agents in the workspace, newest first."""
    q = (
        db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"))
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, WorkflowVersion.workflow_id == Workflow.id)
        .filter(Workflow.workspace_id == workspace_id)
        .order_by(Run.created_at.desc())
    )
    if status:
        q = q.filter(Run.status == status)
    results = []
    for run, wf_id, wf_name in q.offset(offset).limit(limit).all():
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
        )
        results.append(out)
    return results


@workspace_runs_router.get("/{run_id}", response_model=RunWithWorkflowOut)
def get_workspace_run(
    run_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """Single run by ID, scoped to workspace, with workflow name."""
    row = (
        db.query(Run, Workflow.id.label("wf_id"), Workflow.name.label("wf_name"))
        .join(WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id)
        .join(Workflow, WorkflowVersion.workflow_id == Workflow.id)
        .filter(Workflow.workspace_id == workspace_id, Run.id == run_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
    run, wf_id, wf_name = row
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
    )
