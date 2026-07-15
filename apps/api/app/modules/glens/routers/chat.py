"""
POST /glens/chat            — conversational governance reporting
GET  /glens/sessions        — list persisted chat sessions
GET  /glens/sessions/{id}   — restore a session
"""
import json
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.glens.inference import chat as qwen_chat
from app.modules.glens.models import GlensChatSession
from app.modules.glens.prompts import build_system_prompt

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/glens", tags=["glens"])


def _parse_workspace_id(workspace_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace_id")


def _parse_session_id(session_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid session_id")


def _get_session(db: Session, session_id: str, ws_uuid: uuid.UUID) -> GlensChatSession:
    session = db.query(GlensChatSession).filter(
        GlensChatSession.id == _parse_session_id(session_id),
        GlensChatSession.workspace_id == ws_uuid,
    ).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class SessionOut(BaseModel):
    id: str
    title: str
    created_at: str
    has_dashboard: bool


@router.post("/chat")
async def glens_chat(
    req: ChatRequest,
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = _parse_workspace_id(workspace_id)
    logger = log.bind(workspace_id=workspace_id)

    session = None
    if req.session_id:
        session = _get_session(db, req.session_id, ws_uuid)
        logger = logger.bind(session_id=req.session_id)

    if not session:
        session = GlensChatSession(
            workspace_id=ws_uuid,
            title=req.message[:60],
            messages=json.dumps([{"role": "system", "content": build_system_prompt()}]),
        )
        db.add(session)
        db.flush()
        logger = logger.bind(session_id=str(session.id))

    messages = json.loads(session.messages)
    messages.append({"role": "user", "content": req.message})

    try:
        raw = qwen_chat(messages, session_id=str(session.id))
    except Exception as e:
        logger.error("glens.chat.inference_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Inference unavailable — model may be cold, retry in 30s")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("glens.chat.parse_failed", raw=raw[:200])
        parsed = {"ready": False, "question": raw}

    messages.append({"role": "assistant", "content": raw})
    session.messages = json.dumps(messages)

    if parsed.get("ready"):
        session.render_spec = raw
        session.title = parsed.get("title", session.title)[:60]

    session.updated_at = datetime.now(timezone.utc)
    db.commit()

    logger.info("glens.chat.complete", ready=parsed.get("ready", False))

    return {
        "session_id": str(session.id),
        "ready": parsed.get("ready", False),
        "question": parsed.get("question"),
        "spec": parsed if parsed.get("ready") else None,
    }


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = _parse_workspace_id(workspace_id)
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
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = _parse_workspace_id(workspace_id)
    session = _get_session(db, session_id, ws_uuid)

    messages = json.loads(session.messages)
    user_messages = [m for m in messages if m["role"] != "system"]

    return {
        "id": str(session.id),
        "title": session.title,
        "messages": user_messages,
        "spec": json.loads(session.render_spec) if session.render_spec else None,
        "created_at": session.created_at.isoformat(),
    }
