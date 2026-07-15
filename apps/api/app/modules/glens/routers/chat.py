"""
POST /glens/chat   — conversational governance reporting
GET  /glens/sessions — list persisted chat sessions
"""
import json
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id
from app.core.database import Base, get_db
from app.modules.glens.inference import chat as qwen_chat
from app.modules.glens.prompts import build_system_prompt

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/glens", tags=["glens"])


# ── Model ─────────────────────────────────────────────────────────────────────

class GlensChatSession(Base):
    __tablename__ = "glens_chat_sessions"

    id           = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    title        = Column(String, nullable=False)
    messages     = Column(Text, nullable=False, default="[]")   # JSON array
    render_spec  = Column(Text, nullable=True)                  # last emitted spec
    created_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))


# ── Schemas ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None   # continue existing session


class SessionOut(BaseModel):
    id: str
    title: str
    created_at: str
    has_dashboard: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/chat")
async def glens_chat(
    req: ChatRequest,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = uuid.UUID(workspace_id)

    # Load or create session
    session = None
    if req.session_id:
        session = db.query(GlensChatSession).filter(
            GlensChatSession.id == uuid.UUID(req.session_id),
            GlensChatSession.workspace_id == ws_uuid,
        ).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

    if not session:
        session = GlensChatSession(
            workspace_id=ws_uuid,
            title=req.message[:60],   # auto-title from first message
            messages=json.dumps([{"role": "system", "content": build_system_prompt()}]),
        )
        db.add(session)
        db.flush()

    # Build message history
    messages = json.loads(session.messages)
    messages.append({"role": "user", "content": req.message})

    # Call Qwen3
    try:
        raw = qwen_chat(messages, session_id=str(session.id))
    except Exception as e:
        log.error("glens.inference.error", error=str(e))
        raise HTTPException(status_code=503, detail="Inference unavailable — model may be cold, retry in 30s")

    # Parse response
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {"ready": False, "question": raw}

    # Persist assistant turn
    messages.append({"role": "assistant", "content": raw})
    session.messages = json.dumps(messages)

    if parsed.get("ready"):
        session.render_spec = raw
        session.title = parsed.get("title", session.title)[:60]

    session.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {
        "session_id": str(session.id),
        "ready": parsed.get("ready", False),
        "question": parsed.get("question"),       # clarifying question if not ready
        "spec": parsed if parsed.get("ready") else None,
    }


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = uuid.UUID(workspace_id)
    sessions = (
        db.query(GlensChatSession)
        .filter(GlensChatSession.workspace_id == ws_uuid)
        .order_by(GlensChatSession.updated_at.desc())
        .limit(50)
        .all()
    )
    return [
        SessionOut(
            id=str(s.id),
            title=s.title,
            created_at=s.created_at.isoformat(),
            has_dashboard=s.render_spec is not None,
        )
        for s in sessions
    ]


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = uuid.UUID(workspace_id)
    session = db.query(GlensChatSession).filter(
        GlensChatSession.id == uuid.UUID(session_id),
        GlensChatSession.workspace_id == ws_uuid,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = json.loads(session.messages)
    # Strip system prompt from response
    user_messages = [m for m in messages if m["role"] != "system"]

    return {
        "id": str(session.id),
        "title": session.title,
        "messages": user_messages,
        "spec": json.loads(session.render_spec) if session.render_spec else None,
        "created_at": session.created_at.isoformat(),
    }
