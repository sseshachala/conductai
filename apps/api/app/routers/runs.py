import json
from uuid import UUID

import redis
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.run import Run, RunEvent
from app.models.workflow import Workflow
from app.schemas.run import RunCreate, RunDetailOut, RunOut

router = APIRouter(prefix="/workflows/{workflow_id}/runs", tags=["runs"])

QUEUE_KEY = "marshal:runs:queue"


def _redis():
    return redis.from_url(settings.redis_url, decode_responses=True)


@router.get("", response_model=list[RunOut])
def list_runs(workflow_id: UUID, db: Session = Depends(get_db)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return (
        db.query(Run)
        .filter(Run.workflow_version_id == workflow.current_version_id)
        .order_by(Run.created_at.desc())
        .all()
    )


@router.post("", response_model=RunOut, status_code=201)
def create_run(workflow_id: UUID, body: RunCreate, db: Session = Depends(get_db)):
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    if not workflow.current_version_id:
        raise HTTPException(status_code=400, detail="Workflow has no published version")

    initial_state = {"__dry_run": True} if body.dry_run else {}
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
def get_run(workflow_id: UUID, run_id: UUID, db: Session = Depends(get_db)):
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}/stream")
def stream_run_events(workflow_id: UUID, run_id: UUID, db: Session = Depends(get_db)):
    """SSE stream of run_events as they are written by the executor."""
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
):
    """
    Called by the human approver (or Slack webhook) to resume a paused run.
    Stores the decision in run.state and re-queues the run.
    """
    if body.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="decision must be 'approved' or 'rejected'")

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "paused":
        raise HTTPException(status_code=400, detail=f"Run is not paused (status: {run.status})")

    block_id = run.current_block_id
    if not block_id:
        raise HTTPException(status_code=400, detail="No approval block recorded on paused run")

    # Record decision into state so executor can resume past the approval block
    state = dict(run.state or {})
    state[f"__approval_{block_id}"] = body.decision
    if body.approver:
        state[f"__approver_{block_id}"] = body.approver
    run.state = state
    run.status = "pending"
    run.paused_at = None
    db.commit()

    # Emit event
    event = RunEvent(
        run_id=run_id,
        block_id=block_id,
        kind="approval_received",
        payload={"decision": body.decision, "approver": body.approver},
    )
    db.add(event)
    db.commit()

    # Re-queue for the worker
    _redis().rpush(QUEUE_KEY, str(run_id))

    return {"run_id": str(run_id), "decision": body.decision, "status": "queued"}
