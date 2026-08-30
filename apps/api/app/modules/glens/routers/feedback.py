"""Thumbs up/down feedback on individual assistant messages.

Split out of chat.py in #1459.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.glens.models import GlensChatFeedback, GlensChatSession

from ._helpers import _parse_workspace_id

router = APIRouter(prefix="/glens", tags=["glens"])


class FeedbackIn(BaseModel):
    session_id: str
    message_id: str                    # position/id of the assistant message
    verdict: str                        # "up" | "down"
    comment: str | None = None


@router.post("/chat/feedback")
def submit_feedback(
    req: FeedbackIn,
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str | None = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Record thumbs up/down for one assistant message. Upsert on
    (session_id, message_id, clerk_user_id) — a user can flip their vote
    or add a comment; latest wins.

    Downstream: aggregated feedback feeds the LLM tuning + prompt
    regression loop (nightly rollup, not part of this endpoint).
    """
    if req.verdict not in ("up", "down"):
        raise HTTPException(status_code=400, detail="verdict must be 'up' or 'down'")
    if not req.message_id.strip():
        raise HTTPException(status_code=400, detail="message_id is required")
    if req.comment is not None and len(req.comment) > 2000:
        raise HTTPException(status_code=400, detail="comment must be <= 2000 chars")

    ws_uuid = _parse_workspace_id(workspace_id)
    try:
        session_uuid = uuid.UUID(req.session_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="session_id is not a UUID")

    # Confirm the session belongs to this workspace so users can't leave
    # feedback on someone else's session by guessing the id.
    session = (
        db.query(GlensChatSession)
        .filter(
            GlensChatSession.id == session_uuid,
            GlensChatSession.workspace_id == ws_uuid,
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")

    existing = (
        db.query(GlensChatFeedback)
        .filter(
            GlensChatFeedback.session_id == session_uuid,
            GlensChatFeedback.message_id == req.message_id,
            GlensChatFeedback.clerk_user_id == user_id,
        )
        .first()
    )

    now = datetime.now(timezone.utc)
    if existing:
        existing.verdict = req.verdict
        existing.comment = req.comment
        existing.updated_at = now
        db.commit()
        return {"ok": True, "action": "updated", "verdict": req.verdict}

    db.add(GlensChatFeedback(
        workspace_id=ws_uuid,
        session_id=session_uuid,
        message_id=req.message_id,
        verdict=req.verdict,
        comment=req.comment,
        clerk_user_id=user_id,
    ))
    db.commit()
    return {"ok": True, "action": "created", "verdict": req.verdict}
