"""
POST /glens/chat            — conversational governance reporting
GET  /glens/sessions        — list persisted chat sessions
GET  /glens/sessions/{id}   — restore a session
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.models.workspace_config import WorkspaceConfig
from app.modules.glens.agent import Agent
from app.modules.glens.router import route
from app.modules.glens.models import GlensChatSession
from app.modules.glens.prompts import KPI_META, CHART_META, TABLE_META, VALID_KPIS, VALID_CHARTS, VALID_TABLES
from app.modules.guard.models import GuardAuditEvent
from app.modules.guard.routers.spend import _get_spend_summary_inner, _org_ws_subquery

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
            messages=json.dumps([]),
        )
        db.add(session)
        db.flush()
        logger = logger.bind(session_id=str(session.id))

    messages = json.loads(session.messages)
    messages.append({"role": "user", "content": req.message})

    # Route → pick skills → run agent
    guard_ctx = _fetch_guard_context(db, workspace_id)
    try:
        skills = await asyncio.to_thread(route, req.message)
        agent = Agent(skills)
        parsed = await asyncio.to_thread(agent.run, messages[-20:], guard_ctx)
    except Exception as e:
        logger.error("glens.chat.inference_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Inference unavailable — model may be cold, retry in 30s")

    # Persist raw response as assistant turn
    messages.append({"role": "assistant", "content": json.dumps(parsed)})
    session.messages = json.dumps(messages)

    spec = None
    skill = parsed.get("skill", "report")

    if skill == "report" and parsed.get("ready"):
        spec = _build_spec(
            title=parsed.get("title", "Guard Overview"),
            month=parsed.get("month", ""),
            kpi_picks=parsed.get("kpis", []),
            chart_picks=parsed.get("charts", []),
            table_picks=parsed.get("tables", []),
        )
        session.render_spec = json.dumps(spec)
        session.title = parsed.get("title", session.title)[:60]

    session.updated_at = datetime.now(timezone.utc)
    db.commit()

    # Normalize answer field across all skills
    answer_text = parsed.get("answer") or parsed.get("question")
    logger.info("glens.chat.complete", skill=skill, ready=bool(spec))

    return {
        "session_id": str(session.id),
        "skill": skill,
        "ready": spec is not None,
        "question": answer_text,
        "spec": spec,
    }


def _fetch_guard_context(db: Session, workspace_id: str) -> dict:
    try:
        spend = _get_spend_summary_inner(db, workspace_id, None)
        spend_data = {
            "events_today": spend.events_today,
            "blocked_today": spend.blocked_today,
            "total_cost_usd": round(spend.total_cost_usd, 2),
            "active_developers": spend.active_developers,
            "tokens_saved_today": spend.tokens_saved_today,
            "sessions": spend.sessions,
            "hook_sessions": spend.hook_sessions,
            "by_ai_tool": [{"tool": t.ai_tool, "cost_usd": round(t.cost_usd, 2)} for t in spend.by_ai_tool],
            "by_developer": [{"email": d.email, "cost_usd": round(d.cost_usd, 2)} for d in spend.by_developer],
        }
    except Exception:
        spend_data = {}

    try:
        org_ws = _org_ws_subquery(db, workspace_id)
        rows = (
            db.query(GuardAuditEvent)
            .filter(GuardAuditEvent.workspace_id.in_(org_ws))
            .order_by(GuardAuditEvent.ts.desc())
            .limit(20)
            .all()
        )
        events_data = [
            {"ts": e.ts.isoformat(), "decision": e.decision, "user_email": e.user_email, "ai_tool": e.ai_tool, "rule_id": e.rule_id}
            for e in rows
        ]
    except Exception:
        events_data = []

    return {"spend": spend_data, "recent_events": events_data}


def _build_spec(title: str, month: str, kpi_picks: list, chart_picks: list, table_picks: list) -> dict:
    """Assemble spec from model's validated picks — model selects, backend wires."""
    spend_ep = f"/guard/spend{f'?month={month}' if month else ''}"

    kpis = [
        {"label": KPI_META[k]["label"], "endpoint": spend_ep, "field": KPI_META[k]["field"]}
        for k in kpi_picks if k in VALID_KPIS
    ]
    charts = [
        {"type": "bar", "endpoint": spend_ep, **CHART_META[c]}
        for c in chart_picks if c in VALID_CHARTS
    ]
    tables = [
        TABLE_META[t]
        for t in table_picks if t in VALID_TABLES
    ]

    # Fallback: if model picked nothing, give a sensible overview
    if not kpis:
        kpis = [
            {"label": "Events Today",    "endpoint": spend_ep, "field": "events_today"},
            {"label": "Blocks Today",    "endpoint": spend_ep, "field": "blocked_today"},
            {"label": "Total Cost",      "endpoint": spend_ep, "field": "total_cost_usd"},
            {"label": "Active Devs",     "endpoint": spend_ep, "field": "active_developers"},
        ]

    return {"title": title, "kpis": kpis, "charts": charts, "tables": tables}


_GLENS_KEY = "glens_enabled"


def _glens_row(db: Session, ws_uuid: uuid.UUID):
    return db.query(WorkspaceConfig).filter(
        WorkspaceConfig.workspace_id == ws_uuid,
        WorkspaceConfig.key == _GLENS_KEY,
    ).first()


@router.get("/status")
def glens_status(
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = _parse_workspace_id(workspace_id)
    return {"installed": _glens_row(db, ws_uuid) is not None}


@router.post("/install", status_code=201)
def glens_install(
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = _parse_workspace_id(workspace_id)
    if not _glens_row(db, ws_uuid):
        db.add(WorkspaceConfig(workspace_id=ws_uuid, key=_GLENS_KEY, value="true"))
        db.commit()
    log.info("glens.installed", workspace_id=workspace_id)
    return {"installed": True}


@router.delete("/install")
def glens_uninstall(
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = _parse_workspace_id(workspace_id)
    db.query(WorkspaceConfig).filter(
        WorkspaceConfig.workspace_id == ws_uuid,
        WorkspaceConfig.key == _GLENS_KEY,
    ).delete(synchronize_session=False)
    db.commit()
    log.info("glens.uninstalled", workspace_id=workspace_id)
    return {"installed": False}


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(
    session_id: str,
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = _parse_workspace_id(workspace_id)
    db.query(GlensChatSession).filter(
        GlensChatSession.id == _parse_session_id(session_id),
        GlensChatSession.workspace_id == ws_uuid,
    ).delete(synchronize_session=False)
    db.commit()
    log.info("glens.session_deleted", workspace_id=workspace_id, session_id=session_id)


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
