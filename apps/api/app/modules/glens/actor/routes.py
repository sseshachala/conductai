"""Actor endpoints — Confirm / Cancel a pending Lens-proposed action.

Thin wrappers around `dispatch_confirm` / `dispatch_cancel` in `helpers.py`.
The same helpers back the LLM-callable `confirm_pending_action` /
`cancel_pending_action` tools (#1465), so the button click and the chat "yes"
resolve to identical server behavior.
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
from app.modules.glens.actor.helpers import (
    ConfirmError,
    dispatch_cancel,
    dispatch_confirm,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/glens/actions", tags=["glens", "actor"])


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

    - Only the original requester can decide their own proposal.
    - Row must be `pending` and not expired.
    - Runs `spec.execute()` and stores the result on the row for idempotency.
    """
    decider_email = get_clerk_user_email(user_id) if user_id else None
    try:
        payload = dispatch_confirm(
            db,
            action_id=action_id,
            workspace_id=workspace_id,
            clerk_user_id=user_id,
            user_email=decider_email,
            role=role,
            session_id=None,  # HTTP callers don't carry chat session context
        )
    except ConfirmError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    return ConfirmResponse(
        executed=payload["executed"],
        action_id=payload["action_id"],
        tool_name=payload["tool_name"],
        status=payload["status"],
        result=payload.get("result"),
    )


@router.post("/{action_id}/cancel", response_model=CancelResponse)
def cancel_action(
    action_id: str,
    workspace_id: str = Depends(get_workspace_id),
    user_id: Annotated[str | None, Depends(get_user_id)] = None,
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("platform.approvals.decide")),
) -> CancelResponse:
    decider_email = get_clerk_user_email(user_id) if user_id else None
    try:
        payload = dispatch_cancel(
            db,
            action_id=action_id,
            workspace_id=workspace_id,
            clerk_user_id=user_id,
            user_email=decider_email,
            session_id=None,
        )
    except ConfirmError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)

    return CancelResponse(
        cancelled=payload["cancelled"],
        action_id=payload["action_id"],
        tool_name=payload["tool_name"],
    )
