"""
POST /share          — create a time-limited share token for a resource (auth required)
GET  /share/{token}  — resolve token and return resource data (public, no auth)

Tokens are stored in Redis with a 2-hour TTL.
Supported resource types: session_report
"""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id
from app.core.config import settings
from app.core.database import get_db
from app.modules.guard.models import SessionReport

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/share", tags=["share"])

_TTL_SECONDS = 7200  # 2 hours


def _redis():
    import redis as _redis_lib
    return _redis_lib.Redis.from_url(settings.redis_url, decode_responses=True)


# ── Schemas ───────────────────────────────────────────────────────────────────

class ShareRequest(BaseModel):
    resource_type: str   # "session_report"
    resource_id: str


class ShareResponse(BaseModel):
    share_url: str
    token: str
    expires_at: str


# ── POST /share ───────────────────────────────────────────────────────────────

@router.post("", response_model=ShareResponse)
def create_share_link(
    body: ShareRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
) -> ShareResponse:
    if body.resource_type not in {"session_report"}:
        raise HTTPException(status_code=400, detail=f"Unsupported resource_type: {body.resource_type}")

    # Verify the resource exists and belongs to this workspace before issuing a token
    _fetch_resource(db, body.resource_type, body.resource_id, workspace_id)

    token = secrets.token_urlsafe(16)
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=_TTL_SECONDS)

    payload = {
        "resource_type": body.resource_type,
        "resource_id": body.resource_id,
        "workspace_id": workspace_id,
        "expires_at": expires_at.isoformat(),
    }
    _redis().setex(f"share:{token}", _TTL_SECONDS, json.dumps(payload))

    base = settings.app_url.rstrip("/") if hasattr(settings, "app_url") and settings.app_url else ""
    share_url = f"{base}/share/{token}"

    log.info("share.created", resource_type=body.resource_type, resource_id=body.resource_id, workspace_id=workspace_id)
    return ShareResponse(share_url=share_url, token=token, expires_at=expires_at.isoformat())


# ── GET /share/{token} ────────────────────────────────────────────────────────

@router.get("/{token}")
def resolve_share(token: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    raw = _redis().get(f"share:{token}")
    if not raw:
        raise HTTPException(status_code=404, detail="Share link not found or expired")

    payload = json.loads(raw)
    resource_type = payload["resource_type"]
    resource_id   = payload["resource_id"]
    workspace_id  = payload["workspace_id"]

    data = _fetch_resource(db, resource_type, resource_id, workspace_id)
    return {
        "resource_type": resource_type,
        "expires_at": payload["expires_at"],
        "data": data,
    }


# ── Internal fetch ────────────────────────────────────────────────────────────

def _fetch_resource(db: Session, resource_type: str, resource_id: str, workspace_id: str) -> dict[str, Any]:
    if resource_type == "session_report":
        try:
            rid = uuid.UUID(resource_id)
            wid = uuid.UUID(workspace_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid resource_id or workspace_id")

        r = (
            db.query(SessionReport)
            .filter(SessionReport.id == rid, SessionReport.workspace_id == wid)
            .first()
        )
        if not r:
            raise HTTPException(status_code=404, detail="Resource not found")

        return {
            "id": str(r.id),
            "workspace_id": str(r.workspace_id),
            "developer_email": r.developer_email,
            "archetype": r.archetype,
            "autonomy_score": r.autonomy_score,
            "planning_ratio": r.planning_ratio,
            "sessions": r.sessions,
            "prompts": r.prompts,
            "commits": r.commits,
            "lines_per_hour": r.lines_per_hour,
            "active_days": r.active_days,
            "tools_json": r.tools_json,
            "report_md": r.report_md,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    raise HTTPException(status_code=400, detail=f"Unknown resource_type: {resource_type}")
