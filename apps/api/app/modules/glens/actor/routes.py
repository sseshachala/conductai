"""Actor endpoints — Confirm / Cancel a pending Lens-proposed action.

The confirm route calls `apply_decision` on the underlying
`guard_approval_requests` row (same as Slack/Guard UI/direct API), then
dispatches to `spec.execute()` — the real mutation. Cancel just rejects
the row.

Idempotency: `apply_decision` moves the row from `pending` to
`approved|rejected` in a single UPDATE; the substrate checks status before
dispatching so double-clicks return the cached result rather than firing
`execute()` twice.
"""
from __future__ import annotations

from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import (
    get_clerk_user_email,
    get_user_id,
    get_user_workspace_role,
    get_workspace_id,
    require_permission,
)
from app.core.database import get_db
from app.modules.glens.actor.registry import default_action_registry
from app.modules.glens.actor.types import ActionCtx
from app.modules.guard.approval import (
    apply_decision,
    can_decide,
    sweep_if_timed_out,
)
from app.modules.guard.models import GuardApprovalRequest

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/glens/actions", tags=["glens", "actor"])


def _get_pending(db: Session, action_id: str, workspace_id: str) -> GuardApprovalRequest:
    import uuid as _uuid
    try:
        aid = _uuid.UUID(action_id)
        ws = _uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid action id")
    row = (
        db.query(GuardApprovalRequest)
        .filter(
            GuardApprovalRequest.id == aid,
            GuardApprovalRequest.workspace_id == ws,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="action not found")
    return row


class ConfirmResponse(BaseModel):
    executed: bool
    action_id: str
    tool_name: str
    status: str
    result: dict[str, Any] | None = None


class CancelResponse(BaseModel):
    cancelled: bool
    action_id: str
    tool_name: str


@router.post("/{action_id}/confirm", response_model=ConfirmResponse)
def confirm_action(
    action_id: str,
    workspace_id: str = Depends(get_workspace_id),
    user_id: Annotated[str | None, Depends(get_user_id)] = None,
    role: Annotated[str, Depends(get_user_workspace_role)] = "viewer",
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("platform.approvals.decide")),
) -> ConfirmResponse:
    """Confirm and dispatch a Lens-proposed action.

    - Only the original requester can confirm their own proposal (peer rule).
    - Row must be `pending` and not expired.
    - Runs `spec.execute()` and stores the result on the row for idempotency.
    """
    row = _get_pending(db, action_id, workspace_id)
    row = sweep_if_timed_out(db, row)

    if row.status != "pending":
        # Idempotent for the "already confirmed" case — return stored result.
        if row.status == "approved" and row.tool_input.get("_execute_result") is not None:
            return ConfirmResponse(
                executed=True, action_id=str(row.id),
                tool_name=row.tool_name, status=row.status,
                result=row.tool_input.get("_execute_result"),
            )
        raise HTTPException(status_code=409, detail=f"action is {row.status}")

    spec = default_action_registry.get(row.tool_name)
    if not spec:
        raise HTTPException(status_code=500, detail=f"no spec registered for {row.tool_name}")

    # Only the proposer can confirm (self-confirmation, not peer approval).
    # This keeps the Lens actor flow "prompt-injection safe" — a compromised
    # LLM in someone else's session can't decide your pending action.
    if row.requester_user_id and user_id and row.requester_user_id != user_id:
        raise HTTPException(status_code=403, detail="only the proposer can confirm")

    decider_email = get_clerk_user_email(user_id) if user_id else row.requester_email
    ok, reason = can_decide(row, decider_email=decider_email, decider_user_id=user_id, decider_role=role)
    if not ok:
        raise HTTPException(status_code=403, detail=reason or "not authorized")

    # Mark the approval as approved (writes hash-chained audit event).
    row = apply_decision(
        db, row,
        decision="approved",
        decider_email=decider_email,
        decider_user_id=user_id,
        reason=f"lens.actor:{row.tool_name}",
    )

    # Dispatch to spec.execute(). If it raises, we still keep the approved
    # row (audit trail) but return 500 with the error string.
    ctx = ActionCtx(
        db=db,
        workspace_id=workspace_id,
        clerk_user_id=user_id,
        user_email=decider_email,
        session_id=row.session_id,
        agent_identity_id=row.requester_agent_ident,
        surface=row.surface or "lens",
    )
    try:
        result = spec.execute(ctx, row.tool_input)
    except Exception as exc:  # noqa: BLE001 — surface up as 500 with detail
        log.warning("lens.actor.execute_failed", tool=row.tool_name, err=str(exc))
        raise HTTPException(status_code=500, detail=f"execute failed: {exc}")

    # Store result on the row for idempotent replay.
    row.tool_input = {**row.tool_input, "_execute_result": result}
    db.commit()

    return ConfirmResponse(
        executed=True,
        action_id=str(row.id),
        tool_name=row.tool_name,
        status=row.status,
        result=result,
    )


@router.post("/{action_id}/cancel", response_model=CancelResponse)
def cancel_action(
    action_id: str,
    workspace_id: str = Depends(get_workspace_id),
    user_id: Annotated[str | None, Depends(get_user_id)] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("platform.approvals.decide")),
) -> CancelResponse:
    row = _get_pending(db, action_id, workspace_id)
    row = sweep_if_timed_out(db, row)
    if row.status != "pending":
        raise HTTPException(status_code=409, detail=f"action is {row.status}")

    if row.requester_user_id and user_id and row.requester_user_id != user_id:
        raise HTTPException(status_code=403, detail="only the proposer can cancel")

    decider_email = get_clerk_user_email(user_id) if user_id else row.requester_email
    apply_decision(
        db, row,
        decision="rejected",
        decider_email=decider_email,
        decider_user_id=user_id,
        reason=f"lens.actor.cancelled:{row.tool_name}",
    )
    return CancelResponse(cancelled=True, action_id=str(row.id), tool_name=row.tool_name)
