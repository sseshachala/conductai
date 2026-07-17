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
from app.modules.glens.coordinator import coordinate
from app.modules.glens.executor import Executor
from app.modules.glens.planner import plan
from app.modules.glens.models import GlensChatSession
from app.modules.glens.prompts import KPI_META, CHART_META, TABLE_META, VALID_KPIS, VALID_CHARTS, VALID_TABLES
from app.modules.guard.models import WorkspaceCustomRule

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

    # Plan → run Agent per subtask → Coordinate
    executor = Executor(db, workspace_id)
    try:
        subtasks = await asyncio.to_thread(plan, req.message)

        results = []
        for subtask in subtasks:
            skill = subtask.get("skill", "report")
            agent = Agent([skill])
            sub_messages = messages[-20:].copy()
            if len(subtasks) > 1:
                sub_messages = sub_messages[:-1] + [{"role": "user", "content": subtask["question"]}]
            result = await asyncio.to_thread(agent.run, sub_messages, executor)
            results.append(result)

        parsed = coordinate(results)
    except Exception as e:
        logger.error("glens.chat.inference_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Inference unavailable — model may be cold, retry in 30s")

    # Persist raw response as assistant turn
    messages.append({"role": "assistant", "content": json.dumps(parsed)})
    session.messages = json.dumps(messages)

    spec = None
    skill = parsed.get("skill", "report")

    # Policy write — return draft for frontend confirmation; do not build spec
    if parsed.get("confirm_required"):
        session.updated_at = datetime.now(timezone.utc)
        db.commit()
        return {
            "session_id": str(session.id),
            "skill": "policy",
            "ready": False,
            "confirm_required": True,
            "action": parsed.get("action"),
            "answer": parsed.get("answer"),
            "draft": parsed.get("draft"),
            "mapping": parsed.get("mapping", []),
            "target_rule_id": parsed.get("target_rule_id"),
        }

    if parsed.get("ready"):
        # Coordinator may return a pre-merged spec, or report skill returns picks
        if parsed.get("spec"):
            spec = parsed["spec"]
        else:
            spec = _build_spec(
                title=parsed.get("title", "Guard Overview"),
                month=parsed.get("month", ""),
                kpi_picks=parsed.get("kpis", []),
                chart_picks=parsed.get("charts", []),
                table_picks=parsed.get("tables", []),
            )
        session.render_spec = json.dumps(spec)
        session.title = parsed.get("title", spec.get("title", session.title))[:60]

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


class PolicyApplyRequest(BaseModel):
    action: str                          # "create" | "patch"
    draft: dict
    target_rule_id: str | None = None


@router.post("/policy/apply", status_code=201)
def policy_apply(
    req: PolicyApplyRequest,
    _: str = Depends(require_permission("guard.policies.edit")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = _parse_workspace_id(workspace_id)

    if req.action == "create":
        rule_id = req.draft.get("rule_id")
        if not rule_id:
            raise HTTPException(status_code=400, detail="draft.rule_id is required")
        existing = db.query(WorkspaceCustomRule).filter(
            WorkspaceCustomRule.workspace_id == ws_uuid,
            WorkspaceCustomRule.rule_id == rule_id,
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Rule '{rule_id}' already exists")
        body = {k: v for k, v in req.draft.items() if k not in ("rule_id", "persona")}
        body["id"] = rule_id
        rule = WorkspaceCustomRule(
            workspace_id=ws_uuid,
            rule_id=rule_id,
            persona=req.draft.get("persona", "agent"),
            body=body,
            enabled=True,
        )
        db.add(rule)
        db.commit()
        log.info("glens.policy.created", workspace_id=workspace_id, rule_id=rule_id)
        return {"ok": True, "rule_id": rule_id, "action": "created"}

    elif req.action == "patch":
        rule_id = req.target_rule_id
        if not rule_id:
            raise HTTPException(status_code=400, detail="target_rule_id is required for patch")
        rule = db.query(WorkspaceCustomRule).filter(
            WorkspaceCustomRule.workspace_id == ws_uuid,
            WorkspaceCustomRule.rule_id == rule_id,
        ).first()
        if not rule:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
        if "enabled" in req.draft:
            rule.enabled = req.draft["enabled"]
        body_patch = {k: v for k, v in req.draft.items() if k != "enabled"}
        if body_patch:
            rule.body = {**rule.body, **body_patch}
        rule.updated_at = datetime.now(timezone.utc)
        db.commit()
        log.info("glens.policy.patched", workspace_id=workspace_id, rule_id=rule_id)
        return {"ok": True, "rule_id": rule_id, "action": "patched"}

    raise HTTPException(status_code=400, detail=f"Unknown action '{req.action}'")


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
