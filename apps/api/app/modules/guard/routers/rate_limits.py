"""Rate limit CRUD (#980).

GET    /guard/rate-limits            — list legacy default + agent-wide caps
PUT    /guard/rate-limits            — upsert (agent_identity_id=None => legacy default)
DELETE /guard/rate-limits/{id}       — remove cap

Gateway v2 admits profile + agent-wide caps atomically in gateway_profile_rate_limit.
The legacy proxy retains its existing workspace-default enforcement.
"""
from __future__ import annotations

import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.guard.models import GuardRateLimit
from app.modules.agent_identity.models import AgentIdentity
from app.modules.agent_identity.labels import agent_options


log = structlog.get_logger(__name__)

router = APIRouter(prefix="/guard/rate-limits", tags=["guard"])


class RateLimitIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_identity_id: Optional[uuid.UUID] = None
    rpm: Optional[int] = Field(default=None, strict=True, gt=0, le=2147483647)
    tpm: Optional[int] = Field(default=None, strict=True, gt=0, le=2147483647)


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


@router.get("/agents")
def list_agent_options(
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.spend.budgets.edit")),
    db: Session = Depends(get_db),
):
    agents = db.query(AgentIdentity).filter(AgentIdentity.workspace_id == workspace_id).order_by(
        AgentIdentity.name, AgentIdentity.id,
    ).all()
    return agent_options(db, workspace_id, agents)


@router.put("", response_model=RateLimitOut)
def upsert_rate_limit(
    body: RateLimitIn,
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.spend.budgets.edit")),
    db: Session = Depends(get_db),
):
    ws = uuid.UUID(workspace_id)
    aid = str(body.agent_identity_id) if body.agent_identity_id else None
    if aid and not db.query(AgentIdentity).filter(
        AgentIdentity.id == aid, AgentIdentity.workspace_id == workspace_id,
    ).with_for_update().first():
        raise HTTPException(404, "Agent identity not found in this workspace.")

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
