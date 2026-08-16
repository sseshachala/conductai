"""ConductGuard approval endpoints (#1140).

HITL API for Guard rules with action=approval. Creation is internal (called
from mcp.py/proxy.py/guard_block.py); these endpoints let a human list,
inspect, stream, and decide requests.

Endpoints
---------
GET    /guard/approvals?status=pending           — inbox (perm: platform.approvals.decide)
GET    /guard/approvals/{id}                     — detail + lazy timeout sweep
POST   /guard/approvals/{id}/decide              — approve or reject (peer-check enforced)
GET    /guard/approvals/{id}/stream              — SSE, waits for status change
"""
from __future__ import annotations

import asyncio
import json
import uuid as _uuid
from datetime import datetime, timezone
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import (
    get_clerk_user_email,
    get_user_id,
    get_user_workspace_role,
    get_workspace_id,
    require_permission,
)
from app.core.database import get_db
from app.models.run import Run, RunEvent
from app.modules.guard.approval import (
    apply_decision,
    approval_url,
    can_decide,
    sweep_if_timed_out,
)
from app.modules.guard.models import GuardApprovalRequest

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/guard/approvals", tags=["guard-approvals"])


# ── Pydantic ─────────────────────────────────────────────────────────────────

class ApprovalOut(BaseModel):
    id: str
    workspace_id: str
    rule_id: str
    rule_pack: str | None
    rule_message: str | None
    tool_name: str | None
    tool_input: dict
    requester_email: str | None
    requester_agent_ident: str | None
    surface: str
    session_id: str | None
    source_run_id: str | None
    source_block_id: str | None
    approval_group: str | None
    approval_type: str
    status: str
    decided_by_email: str | None
    decided_reason: str | None
    decided_at: datetime | None
    latency_ms: int | None
    created_at: datetime
    timeout_at: datetime
    url: str


class ListOut(BaseModel):
    workspace_id: str
    items: list[ApprovalOut]


class DecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str | None = Field(default=None, max_length=2000)


class DecisionOut(BaseModel):
    request: ApprovalOut
    run_resumed: bool


# ── helpers ──────────────────────────────────────────────────────────────────

def _serialize(row: GuardApprovalRequest) -> ApprovalOut:
    return ApprovalOut(
        id=str(row.id),
        workspace_id=str(row.workspace_id),
        rule_id=row.rule_id,
        rule_pack=row.rule_pack,
        rule_message=row.rule_message,
        tool_name=row.tool_name,
        tool_input=row.tool_input or {},
        requester_email=row.requester_email,
        requester_agent_ident=row.requester_agent_ident,
        surface=row.surface,
        session_id=row.session_id,
        source_run_id=str(row.source_run_id) if row.source_run_id else None,
        source_block_id=row.source_block_id,
        approval_group=row.approval_group,
        approval_type=row.approval_type,
        status=row.status,
        decided_by_email=row.decided_by_email,
        decided_reason=row.decided_reason,
        decided_at=row.decided_at,
        latency_ms=row.latency_ms,
        created_at=row.created_at,
        timeout_at=row.timeout_at,
        url=approval_url(row.id),
    )


def _get_row(db: Session, req_id: str, workspace_id: str) -> GuardApprovalRequest:
    try:
        req_uuid = _uuid.UUID(req_id)
        ws_uuid = _uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid id")
    row = (
        db.query(GuardApprovalRequest)
        .filter(
            GuardApprovalRequest.id == req_uuid,
            GuardApprovalRequest.workspace_id == ws_uuid,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="approval request not found")
    return row


def _resume_workflow_run(
    db: Session,
    row: GuardApprovalRequest,
    *,
    decision: str,
    decider_email: str | None,
) -> bool:
    """When the approval was triggered from inside a workflow run, mirror the
    existing DSL approve_run flow so the run resumes (approved) or terminates
    (rejected). Returns True when a run was actually resumed/cancelled."""
    if not row.source_run_id or not row.source_block_id:
        return False

    run = db.query(Run).filter(Run.id == row.source_run_id).first()
    if not run:
        return False

    from sqlalchemy import text as _text
    if decision == "approved":
        state = dict(run.state or {})
        state[f"__approval_{row.source_block_id}"] = "approved"
        state[f"__approval_id_{row.source_block_id}"] = str(row.id)
        if decider_email:
            state[f"__approver_{row.source_block_id}"] = decider_email

        cas = db.execute(
            _text(
                "UPDATE runs SET status='pending', paused_at=NULL, state=:state::jsonb "
                "WHERE id=:id AND status='paused' "
                "RETURNING id"
            ),
            {"state": json.dumps(state), "id": str(row.source_run_id)},
        ).fetchone()
        if not cas:
            # Run already resumed by another decider or terminal — still record
            # the decision on the approval row but don't try to re-enqueue.
            log.warning(
                "guard.approval.resume_cas_miss",
                run_id=str(row.source_run_id),
                request_id=str(row.id),
            )
            return False

        db.add(RunEvent(
            run_id=row.source_run_id,
            block_id=row.source_block_id,
            kind="approval_received",
            payload={
                "decision": decision,
                "approver": decider_email,
                "approval_id": str(row.id),
                "source": "guard.rule",
                "rule_id": row.rule_id,
            },
        ))
        db.commit()
        try:
            from app.routers.runs import _enqueue_run, publish_run_event
            _enqueue_run(str(row.source_run_id))
            publish_run_event(str(row.source_run_id))
        except Exception as exc:
            log.warning("guard.approval.enqueue_failed", err=str(exc), run_id=str(row.source_run_id))
        return True

    # rejected — cancel the run so it doesn't sit paused forever.
    cas = db.execute(
        _text(
            "UPDATE runs SET status='cancelled', completed_at=:now, paused_at=NULL "
            "WHERE id=:id AND status='paused' "
            "RETURNING id"
        ),
        {"id": str(row.source_run_id), "now": datetime.now(timezone.utc)},
    ).fetchone()
    if not cas:
        return False
    db.add(RunEvent(
        run_id=row.source_run_id,
        block_id=row.source_block_id,
        kind="approval_received",
        payload={
            "decision": decision,
            "approver": decider_email,
            "approval_id": str(row.id),
            "source": "guard.rule",
            "rule_id": row.rule_id,
        },
    ))
    db.commit()
    try:
        from app.routers.runs import publish_run_event
        publish_run_event(str(row.source_run_id))
    except Exception:
        pass
    return True


# ── endpoints ────────────────────────────────────────────────────────────────


class CreateApprovalIn(BaseModel):
    rule_id: str = Field(..., max_length=200)
    rule_pack: str | None = None
    rule_message: str | None = None
    tool_name: str | None = None
    tool_input: dict = Field(default_factory=dict)
    surface: str = "unknown"
    session_id: str | None = None
    approval_group: str | None = None
    approval_type: str = "any_authorized"
    approval_timeout_sec: int = Field(default=1800, ge=60, le=86400)


@router.post("", response_model=ApprovalOut, status_code=201)
def create_approval(
    body: CreateApprovalIn,
    workspace_id: str = Depends(get_workspace_id),
    user_id: Annotated[str | None, Depends(get_user_id)] = None,
    db: Session = Depends(get_db),
) -> ApprovalOut:
    """Create a pending approval request. Called by the CLI hook (and any other
    agent surface that isn't already in-process on the API) when a rule with
    action=approval fires. The caller is authenticated via the standard bearer
    token — the request is attributed to that identity as the requester."""
    from app.modules.guard.approval import create_approval_request, dispatch_approval_notifications

    requester_email = get_clerk_user_email(user_id) if user_id else None
    rule = {
        "id":                   body.rule_id,
        "pack":                 body.rule_pack,
        "message":              body.rule_message,
        "approval_group":       body.approval_group,
        "approval_type":        body.approval_type,
        "approval_timeout_sec": body.approval_timeout_sec,
    }
    req = create_approval_request(
        db,
        workspace_id=workspace_id,
        rule=rule,
        tool_name=body.tool_name,
        tool_input=body.tool_input,
        requester_email=requester_email,
        requester_user_id=user_id,
        surface=body.surface,
        session_id=body.session_id,
    )
    dispatch_approval_notifications(db, req)
    return _serialize(req)



@router.get("", response_model=ListOut)
def list_approvals(
    status: str = Query("pending", pattern="^(pending|approved|rejected|timed_out|all)$"),
    limit: int = Query(50, ge=1, le=200),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("platform.approvals.decide")),
) -> ListOut:
    try:
        ws = _uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid workspace_id")

    q = db.query(GuardApprovalRequest).filter(GuardApprovalRequest.workspace_id == ws)
    if status != "all":
        q = q.filter(GuardApprovalRequest.status == status)
    rows = q.order_by(GuardApprovalRequest.created_at.desc()).limit(limit).all()

    # Lazy timeout sweep so the inbox never shows a stale "pending" row.
    if status in ("pending", "all"):
        now = datetime.now(timezone.utc)
        for r in rows:
            if r.status == "pending" and r.timeout_at <= now:
                sweep_if_timed_out(db, r, now=now)

    return ListOut(workspace_id=workspace_id, items=[_serialize(r) for r in rows])


@router.get("/{request_id}", response_model=ApprovalOut)
def get_approval(
    request_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("platform.approvals.decide")),
) -> ApprovalOut:
    row = _get_row(db, request_id, workspace_id)
    row = sweep_if_timed_out(db, row)
    return _serialize(row)


@router.post("/{request_id}/decide", response_model=DecisionOut)
def decide_approval(
    request_id: str,
    body: DecisionIn,
    workspace_id: str = Depends(get_workspace_id),
    user_id: Annotated[str | None, Depends(get_user_id)] = None,
    role: Annotated[str, Depends(get_user_workspace_role)] = "viewer",
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("platform.approvals.decide")),
) -> DecisionOut:
    row = _get_row(db, request_id, workspace_id)
    row = sweep_if_timed_out(db, row)
    if row.status != "pending":
        raise HTTPException(status_code=409, detail=f"approval already {row.status}")

    decider_email = get_clerk_user_email(user_id) if user_id else None

    ok, reason = can_decide(
        row,
        decider_email=decider_email,
        decider_user_id=user_id,
        decider_role=role,
    )
    if not ok:
        raise HTTPException(status_code=403, detail=reason or "not authorized to decide this approval")

    row = apply_decision(
        db, row,
        decision=body.decision,
        decider_email=decider_email,
        decider_user_id=user_id,
        reason=body.reason,
    )
    run_resumed = _resume_workflow_run(
        db, row, decision=body.decision, decider_email=decider_email,
    )
    return DecisionOut(request=_serialize(row), run_resumed=run_resumed)


@router.get("/{request_id}/stream")
def stream_approval(
    request_id: str,
    workspace_id: str = Query(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("platform.approvals.decide")),
):
    """Server-sent events. Emits one line whenever the row's status changes.
    Timeout after 5min so long-poll clients (CLI hook) can reconnect. Uses
    a simple DB poll every 2s — cheap enough for the low volume of concurrent
    approval streams we expect (typically 1–2 per workspace)."""
    row = _get_row(db, request_id, workspace_id)

    async def event_generator():
        yield f"data: {json.dumps({'status': row.status, 'id': str(row.id)})}\n\n"
        if row.status != "pending":
            yield "data: [DONE]\n\n"
            return

        last_status = row.status
        # Bound the stream to keep long-poll clients honest.
        for _ in range(150):  # 150 * 2s = 5 minutes
            await asyncio.sleep(2.0)
            fresh = db.query(GuardApprovalRequest).filter(
                GuardApprovalRequest.id == row.id,
            ).first()
            if not fresh:
                yield "data: [DONE]\n\n"
                return
            fresh = sweep_if_timed_out(db, fresh)
            if fresh.status != last_status:
                yield f"data: {json.dumps({'status': fresh.status, 'id': str(fresh.id), 'decided_by': fresh.decided_by_email})}\n\n"
                last_status = fresh.status
                if fresh.status != "pending":
                    yield "data: [DONE]\n\n"
                    return
            else:
                yield ": keepalive\n\n"
        yield "data: {\"status\": \"stream_timeout\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
