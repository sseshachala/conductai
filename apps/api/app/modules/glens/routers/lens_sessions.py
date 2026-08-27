"""Lens Sessions ops surface — list + revoke (#1218 Step 3b.5).

Backend endpoints for the Lens Sessions tab on the Agent Identity page.
- GET  /glens/lens-sessions        list active + last 24h sessions
- POST /glens/lens-sessions/{id}/revoke   ops kill switch
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.glens.models import GlensChatSession
from app.modules.guard.models import GuardAuditEvent

router = APIRouter(prefix="/glens/lens-sessions", tags=["lens-sessions"])

DEFAULT_LOOKBACK = timedelta(hours=24)


class LensSessionOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    token_revoked_at: datetime | None
    is_active: bool
    is_idle: bool
    turns: int
    spend_usd: float
    # #1252 — session-scoped AgentIdentity linkage. Null on pre-migration
    # sessions that haven't taken a turn since 0090.
    agent_identity_id: str | None
    agent_identity_name: str | None
    agent_identity_token_prefix: str | None


class LensSessionRevokeOut(BaseModel):
    id: str
    revoked_at: datetime


@router.get("", response_model=list[LensSessionOut])
def list_lens_sessions(
    include_expired: bool = Query(default=False, description="Include sessions >24h old or revoked"),
    _: str = Depends(require_permission("platform.members.manage")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> list[LensSessionOut]:
    """List Lens sessions with turn count + spend.

    Default filter: active + last 24h. Set include_expired=true to see
    revoked and idle-expired sessions."""
    ws_uuid = uuid.UUID(workspace_id)
    now = datetime.now(timezone.utc)
    cutoff = now - DEFAULT_LOOKBACK

    q = db.query(GlensChatSession).filter(GlensChatSession.workspace_id == ws_uuid)
    if not include_expired:
        q = q.filter(
            GlensChatSession.updated_at >= cutoff,
            GlensChatSession.token_revoked_at.is_(None),
        )
    sessions = q.order_by(GlensChatSession.updated_at.desc()).limit(200).all()

    # Batch AgentIdentity lookup for cond_agt_lens_* linkage (#1252).
    from app.modules.agent_identity.models import AgentIdentity
    identity_ids = [s.agent_identity_id for s in sessions if s.agent_identity_id]
    identity_by_id: dict[str, AgentIdentity] = {}
    if identity_ids:
        identity_by_id = {
            ai.id: ai for ai in (
                db.query(AgentIdentity)
                .filter(AgentIdentity.id.in_(identity_ids))
                .all()
            )
        }

    # Batch spend rollup — one query for all sessions in the returned page.
    session_ids = [str(s.id) for s in sessions]
    spend_by_session: dict[str, float] = {}
    if session_ids:
        rows = (
            db.query(
                GuardAuditEvent.hook_session_id,
                func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0),
            )
            .filter(
                GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.ai_tool == "lens",
                GuardAuditEvent.hook_session_id.in_(session_ids),
            )
            .group_by(GuardAuditEvent.hook_session_id)
            .all()
        )
        spend_by_session = {row[0]: float(row[1] or 0.0) for row in rows}

    out: list[LensSessionOut] = []
    for s in sessions:
        # Turn count = user messages in the stored JSON array
        import json as _json
        try:
            messages = _json.loads(s.messages or "[]")
            turns = sum(1 for m in messages if m.get("role") == "user")
        except Exception:
            turns = 0

        is_idle = bool(s.updated_at and (now - s.updated_at) > DEFAULT_LOOKBACK)
        is_active = s.token_revoked_at is None and not is_idle

        identity = identity_by_id.get(s.agent_identity_id) if s.agent_identity_id else None
        out.append(LensSessionOut(
            id=str(s.id),
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
            token_revoked_at=s.token_revoked_at,
            is_active=is_active,
            is_idle=is_idle,
            turns=turns,
            spend_usd=spend_by_session.get(str(s.id), 0.0),
            agent_identity_id=s.agent_identity_id,
            agent_identity_name=identity.name if identity else None,
            agent_identity_token_prefix=identity.token_prefix if identity else None,
        ))
    return out


@router.post("/{session_id}/revoke", response_model=LensSessionRevokeOut)
def revoke_lens_session(
    session_id: uuid.UUID,
    _: str = Depends(require_permission("platform.members.manage")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> LensSessionRevokeOut:
    """Ops kill switch — mark this session's token revoked. Idempotent."""
    ws_uuid = uuid.UUID(workspace_id)
    session = (
        db.query(GlensChatSession)
        .filter(
            GlensChatSession.id == session_id,
            GlensChatSession.workspace_id == ws_uuid,
        )
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Lens session not found")

    if session.token_revoked_at is None:
        session.token_revoked_at = datetime.now(timezone.utc)
        db.commit()

    return LensSessionRevokeOut(
        id=str(session.id),
        revoked_at=session.token_revoked_at,
    )
