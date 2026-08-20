"""Rate limit CRUD (#980).

GET    /guard/rate-limits            — list workspace default + all per-agent overrides
PUT    /guard/rate-limits            — upsert (agent_identity_id=None => workspace default)
DELETE /guard/rate-limits/{id}       — remove override (or default)

Enforcement helper: app.modules.guard.rate_limit.check_rate_limit
Called from _proxy step 4d.2.
"""
from __future__ import annotations

import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.guard.models import GuardRateLimit


log = structlog.get_logger(__name__)

router = APIRouter(prefix="/guard/rate-limits", tags=["guard"])


class RateLimitIn(BaseModel):
    agent_identity_id: Optional[str] = None
    rpm: Optional[int] = None
    tpm: Optional[int] = None


class RateLimitOut(BaseModel):
    id: str
    agent_identity_id: Optional[str]
    rpm: Optional[int]
    tpm: Optional[int]


def _to_out(row: GuardRateLimit) -> RateLimitOut:
    return RateLimitOut(
        id=str(row.id),
        agent_identity_id=str(row.agent_identity_id) if row.agent_identity_id else None,
        rpm=row.rpm,
        tpm=row.tpm,
    )


@router.get("", response_model=list[RateLimitOut])
def list_rate_limits(
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.spend.budgets.edit")),
    db: Session = Depends(get_db),
):
    ws = uuid.UUID(workspace_id)
    rows = db.query(GuardRateLimit).filter(GuardRateLimit.workspace_id == ws).all()
    return [_to_out(r) for r in rows]


@router.put("", response_model=RateLimitOut)
def upsert_rate_limit(
    body: RateLimitIn,
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.spend.budgets.edit")),
    db: Session = Depends(get_db),
):
    if body.rpm is not None and body.rpm <= 0:
        raise HTTPException(400, "rpm must be positive")
    if body.tpm is not None and body.tpm <= 0:
        raise HTTPException(400, "tpm must be positive")

    ws = uuid.UUID(workspace_id)
    aid = uuid.UUID(body.agent_identity_id) if body.agent_identity_id else None

    q = db.query(GuardRateLimit).filter(GuardRateLimit.workspace_id == ws)
    q = q.filter(GuardRateLimit.agent_identity_id == aid) if aid else q.filter(GuardRateLimit.agent_identity_id.is_(None))
    row = q.first()

    if row:
        row.rpm = body.rpm
        row.tpm = body.tpm
    else:
        row = GuardRateLimit(workspace_id=ws, agent_identity_id=aid, rpm=body.rpm, tpm=body.tpm)
        db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete("/{row_id}", status_code=204)
def delete_rate_limit(
    row_id: str,
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.spend.budgets.edit")),
    db: Session = Depends(get_db),
):
    ws = uuid.UUID(workspace_id)
    row = db.query(GuardRateLimit).filter(
        GuardRateLimit.id == uuid.UUID(row_id),
        GuardRateLimit.workspace_id == ws,
    ).first()
    if row:
        db.delete(row)
        db.commit()
    return None
