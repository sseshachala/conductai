import json
from typing import Annotated
from uuid import UUID

import redis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, _verify_clerk_token, _clerk_enabled, DEV_WORKSPACE_ID
from app.core.config import settings
from app.core.database import get_db
from app.models.run import Run, RunEvent
from app.models.workflow import Workflow
from app.schemas.run import RunCreate, RunDetailOut, RunOut

router = APIRouter(prefix="/workflows/{workflow_id}/runs", tags=["runs"])

QUEUE_KEY = "marshal:runs:queue"


def get_workspace_id_sse(
    request: Request,
    workspace_id: str | None = Depends(lambda: None),
) -> str:
    """Auth dependency for SSE endpoints — also accepts token + workspace_id as query params
    because EventSource cannot set custom headers."""
    # Try header-based auth first
    auth_header = request.headers.get("Authorization", "")
    token_qp = request.query_params.get("token")
    ws_qp = request.query_params.get("workspace_id")
    x_ws = request.headers.get("x-workspace-id")

    if not _clerk_enabled():
        return x_ws or ws_qp or DEV_WORKSPACE_ID

    # CLI API key bypasses Clerk
    api_key_qp = request.query_params.get("api_key")
    api_key_hdr = request.headers.get("x-api-key")
    from app.core.config import settings as _settings
    cli_key = _settings.cli_api_key
    if cli_key and (api_key_qp == cli_key or api_key_hdr == cli_key):
        return x_ws or ws_qp or DEV_WORKSPACE_ID

    # Get token from header OR query param
    raw_token = None
    if auth_header.startswith("Bearer "):
        raw_token = auth_header.removeprefix("Bearer ")
    elif token_qp:
        raw_token = token_qp

    if not raw_token:
        raise HTTPException(status_code=401, detail="Authorization required")

    claims = _verify_clerk_token(raw_token)
    if not claims:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    ws = x_ws or ws_qp or claims.get("org_id") or claims.get("sub")
    if not ws:
        raise HTTPException(status_code=401, detail="No workspace in token claims")
    return ws


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


@router.get("", response_model=list[RunOut])
def list_runs(
    workflow_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    workflow = _get_workflow(workflow_id, workspace_id, db)
    return (
        db.query(Run)
        .filter(Run.workflow_version_id == workflow.current_version_id)
        .order_by(Run.created_at.desc())
        .all()
    )


@router.post("", response_model=RunOut, status_code=201)
def create_run(
    workflow_id: UUID,
    body: RunCreate,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    workflow = _get_workflow(workflow_id, workspace_id, db)
    if not workflow.current_version_id:
        raise HTTPException(status_code=400, detail="Workflow has no published version")

    initial_state = body.initial_state or {}
    if body.dry_run:
        initial_state["__dry_run"] = True
    run = Run(
        workflow_version_id=workflow.current_version_id,
        triggered_by=body.triggered_by,
        status="pending",
        state=initial_state,
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
):
    # Verify the workflow belongs to this workspace before exposing run data.
    _get_workflow(workflow_id, workspace_id, db)
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/stream")
def stream_run_events(
    workflow_id: UUID,
    run_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id_sse),
):
    """SSE stream of run_events as they are written by the executor."""
    _get_workflow(workflow_id, workspace_id, db)
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    def event_generator():
        import time
        from app.core.database import SessionLocal

        seen_ids: set = set()
        poll_db = SessionLocal()
        try:
            while True:
                events = (
                    poll_db.query(RunEvent)
                    .filter(RunEvent.run_id == run_id)
                    .order_by(RunEvent.created_at)
                    .all()
                )
                for ev in events:
                    if ev.id not in seen_ids:
                        seen_ids.add(ev.id)
                        data = {
                            "id": str(ev.id),
                            "kind": ev.kind,
                            "block_id": ev.block_id,
                            "payload": ev.payload,
                        }
                        yield f"data: {json.dumps(data)}\n\n"

                poll_db.expire_all()
                current = poll_db.query(Run).filter(Run.id == run_id).first()
                if current and current.status in ("succeeded", "failed", "paused"):
                    if current.status == "paused":
                        yield f"data: {json.dumps({'kind': 'run_paused', 'block_id': current.current_block_id, 'payload': {}})}\n\n"
                    yield "data: [DONE]\n\n"
                    break

                time.sleep(0.5)
        finally:
            poll_db.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Approval endpoints ────────────────────────────────────────────────────────

class ApprovalDecision(BaseModel):
    decision: str  # "approved" or "rejected"
    approver: str | None = None


@router.post("/{run_id}/approve")
def approve_run(
    workflow_id: UUID,
    run_id: UUID,
    body: ApprovalDecision,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """
    Called by the human approver (or Slack webhook) to resume a paused run.
    Stores the decision in run.state and re-queues the run.
    """
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="decision must be 'approved' or 'rejected'")

    _get_workflow(workflow_id, workspace_id, db)

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
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
