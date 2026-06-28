"""
PATCH /guard/sessions/{hook_session_id}/intent — attach parsed session metadata
"""
from __future__ import annotations

from typing import List, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_guard_hook_auth
from app.core.database import get_db
from app.modules.guard.models import GuardAuditEvent, GuardSession

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/guard/sessions", tags=["guard"])


# ── Schema ────────────────────────────────────────────────────────────────────


class SessionIntentIn(BaseModel):
    intent: Optional[str] = Field(None, max_length=300)
    tool_sequence: Optional[List[str]] = Field(None, max_items=200)
    session_parse_status: Optional[str] = Field(None, max_length=20)
    session_parser: Optional[str] = Field(None, max_length=30)


class SessionIntentOut(BaseModel):
    ok: bool
    session_id: Optional[str] = None


# ── Endpoint ──────────────────────────────────────────────────────────────────


@router.patch("/{hook_session_id}/intent", response_model=SessionIntentOut)
def patch_session_intent(
    hook_session_id: str,
    body: SessionIntentIn,
    workspace_id: str = Depends(get_guard_hook_auth),
    db: Session = Depends(get_db),
) -> SessionIntentOut:
    """Attach parsed intent and tool sequence to a guard session.

    Looks up the GuardSession via GuardAuditEvent.hook_session_id scoped to the
    authenticated workspace. No-op (200 ok=True) if the session does not exist —
    the hook fires before any events are guaranteed to be written.
    """
    # Resolve session via audit events — hook_session_id lives on guard_audit_events
    import uuid as _uuid
    from sqlalchemy import text as _text

    row = (
        db.query(GuardAuditEvent.session_id)
        .filter(
            GuardAuditEvent.hook_session_id == hook_session_id,
            GuardAuditEvent.workspace_id == _uuid.UUID(workspace_id),
            GuardAuditEvent.session_id.isnot(None),
        )
        .first()
    )

    if row is None or row.session_id is None:
        # No events yet for this hook session — no-op
        log.info("guard.session_intent.no_session", hook_session_id=hook_session_id)
        return SessionIntentOut(ok=True, session_id=None)

    session = (
        db.query(GuardSession)
        .filter(
            GuardSession.id == row.session_id,
            GuardSession.workspace_id == _uuid.UUID(workspace_id),
        )
        .first()
    )

    if session is None:
        return SessionIntentOut(ok=True, session_id=None)

    if body.intent is not None:
        session.intent = body.intent[:300]
    if body.tool_sequence is not None:
        session.tool_sequence = body.tool_sequence[:200]
    if body.session_parse_status is not None:
        session.session_parse_status = body.session_parse_status[:20]
    if body.session_parser is not None:
        session.session_parser = body.session_parser[:30]

    db.commit()

    log.info(
        "guard.session_intent.updated",
        session_id=str(session.id),
        parser=session.session_parser,
        status=session.session_parse_status,
    )
    return SessionIntentOut(ok=True, session_id=str(session.id))
