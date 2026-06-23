"""POST /telemetry/events — single ingestion route for CLI/booster events.

Auth: workspace member token (Bearer) — same `guard_member_config` validation
the MCP route uses. Per CLAUDE.md, every endpoint has auth at the resource
boundary.

Redaction: `message` and `traceback` are run through redact_secrets() before
insert so that an accidentally-logged credential never lands in the audit
table. Belt-and-suspenders — clients should redact too, but the server is the
backstop.
"""
from __future__ import annotations

import uuid
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text as _sql
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.pii import redact_secrets
from app.modules.telemetry.models import TelemetryEvent

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


class EventIn(BaseModel):
    tool:       Literal["conduct-cli", "agent-booster"]
    version:    str = Field(..., max_length=64)
    event_type: Literal["info", "warning", "error"]
    message:    str = Field(..., max_length=4000)
    traceback:  Optional[str] = Field(None, max_length=20000)
    run_id:     Optional[uuid.UUID] = None
    session_id: Optional[str] = Field(None, max_length=128)
    context:    dict = Field(default_factory=dict)


def _resolve_workspace(
    authorization: Optional[str],
    workspace_id_hint: Optional[str],
    db: Session,
) -> uuid.UUID:
    """Validate Bearer token against guard_member_config, return workspace_id."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        raise HTTPException(status_code=401, detail="empty token")

    # ponytail: hint narrows the lookup when the client sends one, but we still
    # verify the token row exists — the hint is not trusted.
    if workspace_id_hint:
        try:
            ws_uuid = uuid.UUID(workspace_id_hint)
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid workspace_id")
        row = db.execute(
            _sql(
                "SELECT workspace_id FROM guard_member_config "
                "WHERE workspace_id = :w AND member_token = :t AND active = true LIMIT 1"
            ),
            {"w": str(ws_uuid), "t": token},
        ).fetchone()
    else:
        row = db.execute(
            _sql(
                "SELECT workspace_id FROM guard_member_config "
                "WHERE member_token = :t AND active = true LIMIT 1"
            ),
            {"t": token},
        ).fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="invalid token")
    # Normalize to uuid.UUID — on Postgres the row already carries a UUID
    # object, on SQLite (tests) it comes back as a string.
    raw = row.workspace_id
    return raw if isinstance(raw, uuid.UUID) else uuid.UUID(str(raw))


@router.post("/events", status_code=201)
def ingest_event(
    body: EventIn,
    db: Session = Depends(get_db),
    authorization: Optional[str] = Header(None),
    x_workspace_id: Optional[str] = Header(None),
):
    workspace_id = _resolve_workspace(authorization, x_workspace_id, db)

    message_clean, _ = redact_secrets(body.message)
    tb_clean = None
    if body.traceback:
        tb_clean, _ = redact_secrets(body.traceback)

    evt = TelemetryEvent(
        workspace_id=workspace_id,
        run_id=body.run_id,
        tool=body.tool,
        version=body.version[:64],
        event_type=body.event_type,
        message=message_clean[:4000],
        traceback=(tb_clean[:20000] if tb_clean else None),
        session_id=body.session_id,
        context=body.context or {},
    )
    db.add(evt)
    db.commit()
    return {"ok": True, "id": str(evt.id)}
