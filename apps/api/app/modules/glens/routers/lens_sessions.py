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
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.glens.models import GlensChatSession
from app.runtime.accounting import AccountingReader

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
    # Post-#2221 PR 1: caveats Lens's UI must render alongside the number
    # so users can tell "$X reported" apart from "$X, some tokens missing"
    # or "$X plus some unpriced attempts we couldn't cost." Invariants
    # #4 and #9 preserved end-to-end.
    spend_has_partial_or_missing: bool = False
    spend_has_unpriced_attempts: bool = False
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

    # Batch spend rollup via the shared accounting engine.
    # Post-#2221 PR 1 (consumer wiring): every number comes from
    # ``llm_attempt_receipts`` via ``AccountingReader.spend_by_hook_session_ids``
    # so completeness + unpriced flags travel with each figure. Sessions
    # with no receipts (e.g. shadow was off when they ran, or the workspace
    # isn't yet on the canary allowlist) simply do not appear in the map —
    # the fallback below renders them as $0 with no caveat.
    reader = AccountingReader(db)
    session_uuids = [s.id for s in sessions]
    spend_by_session = reader.spend_by_hook_session_ids(
        workspace_id=ws_uuid,
        hook_session_ids=session_uuids,
    )

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
        spend = spend_by_session.get(s.id)
        out.append(LensSessionOut(
            id=str(s.id),
            title=s.title,
            created_at=s.created_at,
            updated_at=s.updated_at,
            token_revoked_at=s.token_revoked_at,
            is_active=is_active,
            is_idle=is_idle,
            turns=turns,
            spend_usd=float(spend.total_cost_usd) if spend is not None else 0.0,
            spend_has_partial_or_missing=(
                spend.has_partial_or_missing if spend is not None else False
            ),
            spend_has_unpriced_attempts=(
                spend.has_unpriced_attempts if spend is not None else False
            ),
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
