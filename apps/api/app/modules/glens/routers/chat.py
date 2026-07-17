"""
POST /glens/chat            — conversational governance reporting
POST /glens/chat/stream     — SSE chat stream with thinking states
GET  /glens/opener          — proactive opening message
GET  /glens/sessions        — list persisted chat sessions
GET  /glens/sessions/{id}   — restore a session
"""
import asyncio
import base64
import csv
import io
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, BaseModel as _Base
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.models.workspace_config import WorkspaceConfig
from app.modules.glens.agent import Agent
from app.modules.glens.coordinator import coordinate
from app.modules.glens.executor import Executor
from app.modules.glens.inference import chat as qwen_chat
from app.modules.glens.models import GlensChatSession
from app.modules.glens.planner import plan
from app.modules.glens.prompts import CHART_META, KPI_META, TABLE_META, VALID_CHARTS, VALID_KPIS, VALID_TABLES
from app.modules.guard.models import GuardConfig, GuardSpendBudget, WorkspaceCustomRule

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/glens", tags=["glens"])


class _Column(_Base):
    key: str
    label: str
    type: Literal["text", "number", "currency", "date", "badge", "percent", "boolean"] = "text"


class _StatItem(_Base):
    label: str
    value: str
    sub: str | None = None
    color: Literal["ok", "err", "warn", "info", "neutral"] | None = None


class _BadgeItem(_Base):
    label: str
    value: str
    badge: Literal["ok", "err", "warn", "info"] | None = None


class _Block(_Base):
    type: Literal["stat-row", "table", "bar-chart", "badge-list"]
    items: list[_StatItem | _BadgeItem] | None = None
    columns: list[_Column] | None = None
    rows: list[dict[str, Any]] | None = None
    title: str | None = None
    x_key: str | None = None
    y_key: str | None = None
    color: str | None = None
    data: list[dict[str, Any]] | None = None


def _sanitize_blocks(raw: list | None) -> list | None:
    if not raw or not isinstance(raw, list):
        return None
    valid = []
    for b in raw:
        if not isinstance(b, dict) or "type" not in b:
            continue
        try:
            valid.append(_Block.model_validate(b).model_dump(exclude_none=True))
        except Exception:
            continue
    return valid or None


def _sanitize_columns(raw: list | None) -> list | None:
    if not raw or not isinstance(raw, list):
        return None
    valid = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        try:
            valid.append(_Column.model_validate(c).model_dump())
        except Exception:
            continue
    return valid or None


def _sanitize_rows(raw: list | None) -> list | None:
    if not raw or not isinstance(raw, list):
        return None
    return [r for r in raw if isinstance(r, dict)] or None


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


def _extract_json(raw: str) -> str:
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip().rstrip("`").strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    return m.group(0) if m else raw


def _safe_json_loads(raw: str | dict | list | None, fallback: Any = None) -> Any:
    if raw is None:
        return fallback
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(_extract_json(raw))
    except Exception:
        return fallback


def _summary_fallback(messages: list[dict], prior: str | None = None) -> str:
    snippets: list[str] = []
    if prior:
        snippets.append(prior)
    for msg in messages[-8:]:
        role = "User" if msg.get("role") == "user" else "Assistant"
        content = msg.get("content", "")
        if isinstance(content, str) and content:
            snippets.append(f"{role}: {content[:160]}")
    return " | ".join(snippets)[-1200:]


def _summarize_messages(messages: list[dict], prior: str | None = None) -> str:
    if not messages:
        return prior or ""
    prompt = (
        "Summarize this GLens governance conversation for future follow-up questions. "
        "Focus on what the user asked, which Guard entities were discussed, and any pending next steps. "
        'Return JSON only: {"summary":"..."}'
    )
    raw = qwen_chat([
        {"role": "system", "content": prompt},
        {"role": "user", "content": json.dumps(messages[-16:])},
    ])
    parsed = _safe_json_loads(raw, {}) or {}
    summary = parsed.get("summary")
    return str(summary).strip() if summary else _summary_fallback(messages, prior)


def _conversation_messages(messages: list[dict], context_summary: str | None) -> list[dict]:
    if context_summary:
        return [{"role": "system", "content": f"Conversation summary: {context_summary}"}] + messages[-10:]
    return messages[-20:]


def _should_refresh_summary(messages: list[dict]) -> bool:
    user_turns = sum(1 for m in messages if m.get("role") == "user")
    return user_turns >= 5 and user_turns % 5 == 0 and len(messages) > 10


def _looks_like_dashboard_spec(spec: dict) -> bool:
    kpis = spec.get("kpis", [])
    return bool(
        isinstance(spec, dict)
        and isinstance(kpis, list)
        and all(isinstance(k, dict) and "endpoint" in k and "field" in k for k in kpis)
    )


def _build_spec(title: str, month: str, kpi_picks: list, chart_picks: list, table_picks: list) -> dict:
    spend_ep = f"/guard/spend{f'?month={month}' if month else ''}"
    kpis = [{**KPI_META[k], "endpoint": spend_ep} for k in kpi_picks if k in VALID_KPIS]
    charts = [{"type": "bar", "endpoint": spend_ep, **CHART_META[c]} for c in chart_picks if c in VALID_CHARTS]
    tables = [TABLE_META[t] for t in table_picks if t in VALID_TABLES]
    if not kpis:
        kpis = [
            {"label": "Events Today", "endpoint": spend_ep, "field": "events_today"},
            {"label": "Blocks Today", "endpoint": spend_ep, "field": "blocked_today", "color": "err"},
            {"label": "Total Cost", "endpoint": spend_ep, "field": "total_cost_usd"},
            {"label": "Active Devs", "endpoint": spend_ep, "field": "active_developers"},
        ]
    return {"title": title, "kpis": kpis, "charts": charts, "tables": tables}


def _build_answer(parsed: dict, spec: dict | None) -> str:
    answer = str(parsed.get("answer") or parsed.get("question") or "").strip()
    if answer:
        return answer
    if parsed.get("confirm_required"):
        action = parsed.get("action") or "review"
        return f"I drafted a {action} change for you. Review it before applying."
    if parsed.get("page_kind") == "activity":
        events = ((parsed.get("data") or {}).get("events") or []) if isinstance(parsed.get("data"), dict) else []
        return f"I found {len(events)} matching Guard activity events."
    if parsed.get("page_kind") == "governance":
        return "I pulled together the latest Guard governance view for you."
    if spec:
        return f"I put together {spec.get('title', 'a Guard overview')} for you."
    if parsed.get("skill") == "extract":
        return "Your export is ready."
    return "I pulled together the latest Guard data for you."


def _default_followups(skill: str, page_kind: str | None = None) -> list[str]:
    if page_kind == "activity":
        return ["Why did this rule trigger?", "Who was affected?", "Show today's blocks"]
    if page_kind == "governance":
        return ["Show blocked events", "Open compliance", "Set up a budget"]
    if skill == "rules":
        return ["Show matching policies", "Disable this rule", "What triggered it most?"]
    if skill == "spend_config":
        return ["Show current budgets", "Who is spending the most?", "Set a workspace budget"]
    if skill == "compliance":
        return ["Open compliance", "Show missing controls", "Show recent governance events"]
    if skill == "discovery":
        return ["Show unprotected agents", "Which agents are high risk?", "Open governance"]
    return ["Show blocked events", "Who was affected?", "Open compliance"]


def _build_attachments(
    parsed: dict,
    spec: dict | None,
    blocks: list | None,
    rows: list | None,
    columns: list | None,
    download: dict | None,
) -> list[dict]:
    attachments: list[dict] = []
    if spec:
        attachments.append({"type": "dashboard", "spec": spec})
    if parsed.get("page_kind") and parsed.get("data"):
        attachments.append({
            "type": "page",
            "page_kind": parsed.get("page_kind"),
            "data": parsed.get("data"),
            "warning": parsed.get("warning"),
        })
    if blocks:
        attachments.append({
            "type": "blocks",
            "blocks": blocks,
            "warning": parsed.get("warning"),
            "skill": parsed.get("skill"),
        })
    if rows:
        attachments.append({
            "type": "table",
            "rows": rows,
            "columns": columns,
            "warning": parsed.get("warning"),
            "skill": parsed.get("skill"),
        })
    if download:
        attachments.append({
            "type": "download",
            "download_url": download["download_url"],
            "download_name": download["download_name"],
            "mime_type": download["mime_type"],
            "label": download["label"],
        })
    return attachments


def _rich_dashboard_blocks(parsed: dict) -> list[dict] | None:
    if not parsed.get("ready"):
        return None
    raw_kpis = parsed.get("kpis")
    if not isinstance(raw_kpis, list) or not raw_kpis or not all(isinstance(k, dict) for k in raw_kpis):
        return None
    items = []
    for kpi in raw_kpis:
        label = kpi.get("label")
        value = kpi.get("value")
        if label is None or value is None:
            continue
        items.append({
            "label": str(label),
            "value": str(value),
            "sub": str(kpi.get("sub")) if kpi.get("sub") else None,
            "color": kpi.get("color"),
        })
    blocks: list[dict] = [{"type": "stat-row", "items": items}] if items else []
    for chart in parsed.get("charts", []) if isinstance(parsed.get("charts"), list) else []:
        if not isinstance(chart, dict):
            continue
        data = chart.get("data")
        if not isinstance(data, list) or not data:
            continue
        first = data[0] if isinstance(data[0], dict) else {}
        x_key = next((k for k in ("framework", "name", "label", "x", "tool", "email") if k in first), None)
        y_key = next((k for k, v in first.items() if isinstance(v, (int, float))), None)
        if x_key and y_key:
            blocks.append({
                "type": "bar-chart",
                "title": chart.get("title") or chart.get("id"),
                "x_key": x_key,
                "y_key": y_key,
                "data": data,
            })
    for table in parsed.get("tables", []) if isinstance(parsed.get("tables"), list) else []:
        if not isinstance(table, dict) or not isinstance(table.get("rows"), list):
            continue
        rows = [row for row in table["rows"] if isinstance(row, dict)]
        if not rows:
            continue
        raw_columns = table.get("columns") or list(rows[0].keys())
        columns = [{"key": str(col), "label": str(col).replace("_", " ").title(), "type": "text"} for col in raw_columns]
        blocks.append({"type": "table", "columns": columns, "rows": rows})
    return blocks or None


def _rows_for_export(dataset: str, payload: Any) -> list[dict[str, Any]]:
    if dataset in {"events", "sessions"}:
        return payload if isinstance(payload, list) else []
    if dataset == "spend" and isinstance(payload, dict):
        if isinstance(payload.get("by_ai_tool"), list) and payload["by_ai_tool"]:
            return payload["by_ai_tool"]
        if isinstance(payload.get("by_developer"), list) and payload["by_developer"]:
            return payload["by_developer"]
        return [{k: v for k, v in payload.items() if not isinstance(v, (list, dict))}]
    return []


def _csv_download(rows: list[dict[str, Any]], stem: str) -> dict | None:
    if not rows:
        return None
    keys = list(dict.fromkeys(k for row in rows for k in row.keys()))
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=keys)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k) for k in keys})
    encoded = base64.b64encode(out.getvalue().encode("utf-8")).decode("ascii")
    return {
        "download_url": f"data:text/csv;base64,{encoded}",
        "download_name": f"{stem}.csv",
        "mime_type": "text/csv",
        "label": "Download CSV",
    }


def _handle_extract(parsed: dict, executor: Executor) -> tuple[dict | None, str | None]:
    dataset = str(parsed.get("dataset") or "events")
    fmt = str(parsed.get("format") or "csv")
    filters = parsed.get("filters") or {}
    tool_by_dataset = {
        "events": "get_recent_events",
        "sessions": "get_sessions",
        "spend": "get_spend_summary",
    }
    tool_name = tool_by_dataset.get(dataset)
    if not tool_name:
        return None, None
    raw = executor.call(tool_name, json.dumps(filters))
    data = _safe_json_loads(raw, [] if dataset != "spend" else {})
    if fmt == "summary":
        if isinstance(parsed.get("content"), str) and parsed["content"].strip():
            return None, parsed["content"].strip()
        rows = _rows_for_export(dataset, data)
        return None, f"I prepared a summary export with {len(rows)} {dataset} rows."
    rows = _rows_for_export(dataset, data)
    return _csv_download(rows, f"glens-{dataset}-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"), None


def _normalize_payload(parsed: dict, session_id: str, executor: Executor) -> dict:
    spec = None
    if parsed.get("spec") and _looks_like_dashboard_spec(parsed["spec"]):
        spec = parsed["spec"]
    elif parsed.get("ready") and _looks_like_dashboard_spec(parsed):
        spec = {
            "title": parsed.get("title", "Guard Overview"),
            "kpis": parsed.get("kpis", []),
            "charts": parsed.get("charts", []),
            "tables": parsed.get("tables", []),
        }
    elif parsed.get("ready") and not parsed.get("confirm_required") and all(isinstance(k, str) for k in parsed.get("kpis", [])):
        spec = _build_spec(
            title=parsed.get("title", "Guard Overview"),
            month=parsed.get("month", ""),
            kpi_picks=parsed.get("kpis", []),
            chart_picks=parsed.get("charts", []),
            table_picks=parsed.get("tables", []),
        )

    blocks = _sanitize_blocks(parsed.get("blocks")) or _sanitize_blocks(_rich_dashboard_blocks(parsed))
    rows = _sanitize_rows(parsed.get("rows"))
    columns = _sanitize_columns(parsed.get("columns"))
    download, extract_answer = (None, None)
    if parsed.get("skill") == "extract":
        download, extract_answer = _handle_extract(parsed, executor)
    answer = extract_answer or _build_answer(parsed, spec)
    followups = parsed.get("followups")
    if not isinstance(followups, list) or not followups:
        followups = _default_followups(str(parsed.get("skill") or "analytics"), parsed.get("page_kind"))

    payload = {
        "session_id": session_id,
        "skill": parsed.get("skill", "report"),
        "ready": spec is not None,
        "answer": answer,
        "question": answer,
        "followups": [str(f).strip() for f in followups if str(f).strip()][:3],
        "confirm_required": bool(parsed.get("confirm_required")),
        "action": parsed.get("action"),
        "draft": parsed.get("draft"),
        "mapping": parsed.get("mapping", []),
        "target_rule_id": parsed.get("target_rule_id"),
        "spec": spec,
        "page_kind": parsed.get("page_kind"),
        "page_data": parsed.get("data"),
        "blocks": blocks,
        "rows": rows,
        "columns": columns,
        "warning": parsed.get("warning"),
        "download_url": download["download_url"] if download else None,
        "download_name": download["download_name"] if download else None,
        "download_mime_type": download["mime_type"] if download else None,
    }
    payload["attachments"] = _build_attachments(parsed, spec, blocks, rows, columns, download)
    return payload


def _format_sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, default=str)}\n\n"


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    page_context: str | None = None


class SessionOut(BaseModel):
    id: str
    title: str
    created_at: str
    has_dashboard: bool


async def _execute_chat(
    req: ChatRequest,
    workspace_id: str,
    db: Session,
    emit: Callable[[str, dict], None] | None = None,
) -> dict:
    ws_uuid = _parse_workspace_id(workspace_id)
    logger = log.bind(workspace_id=workspace_id, page_context=req.page_context)

    session = _get_session(db, req.session_id, ws_uuid) if req.session_id else None
    if not session:
        session = GlensChatSession(
            workspace_id=ws_uuid,
            title=req.message[:60],
            messages=json.dumps([]),
        )
        db.add(session)
        db.flush()
    logger = logger.bind(session_id=str(session.id))

    messages = _safe_json_loads(session.messages, []) or []
    messages.append({"role": "user", "content": req.message})

    last_answer: str | None = None
    for prior in reversed(messages[:-1]):
        if prior.get("role") != "assistant":
            continue
        parsed = _safe_json_loads(prior.get("content"), {})
        if isinstance(parsed, dict) and (parsed.get("answer") or parsed.get("question")):
            last_answer = str(parsed.get("answer") or parsed.get("question"))[:300]
            break

    if emit:
        emit("thinking", {"thinking": "Planning the best way to answer…"})

    executor = Executor(db, workspace_id)
    try:
        subtasks = await asyncio.to_thread(
            plan,
            req.message,
            last_answer,
            req.page_context,
            session.context_summary,
        )
        results = []

        def _agent_event(event: dict) -> None:
            if emit and event.get("type") == "thinking":
                emit("thinking", {"thinking": event.get("thinking")})

        for subtask in subtasks:
            skill = subtask.get("skill", "report")
            agent = Agent([skill])
            sub_messages = _conversation_messages(messages, session.context_summary)
            if len(subtasks) > 1:
                sub_messages = sub_messages[:-1] + [{"role": "user", "content": subtask["question"]}]
            result = await asyncio.to_thread(agent.run, sub_messages, executor, _agent_event)
            results.append(result)

        parsed = coordinate(results)
    except Exception as e:
        logger.error("glens.chat.inference_failed", error=str(e))
        raise HTTPException(status_code=503, detail="Inference unavailable — model may be cold, retry in 30s")

    payload = _normalize_payload(parsed, str(session.id), executor)
    messages.append({"role": "assistant", "content": json.dumps(payload, default=str)})
    session.messages = json.dumps(messages)
    session.title = (payload.get("answer") or req.message or session.title)[:60]
    if payload.get("spec"):
        session.render_spec = json.dumps(payload["spec"])
    if _should_refresh_summary(messages):
        try:
            session.context_summary = await asyncio.to_thread(_summarize_messages, messages[:-10], session.context_summary)
        except Exception as e:
            logger.warning("glens.chat.summary_failed", error=str(e))
    session.updated_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("glens.chat.complete", skill=payload.get("skill"), ready=payload.get("ready"))
    return payload


@router.post("/chat")
async def glens_chat(
    req: ChatRequest,
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    return await _execute_chat(req, workspace_id, db)


@router.post("/chat/stream")
async def glens_chat_stream(
    req: ChatRequest,
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()  # unbounded on purpose for short-lived chat streams
    loop = asyncio.get_running_loop()

    def emit(event: str, payload: dict) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, (event, payload))

    async def worker() -> None:
        try:
            emit("thinking", {"thinking": "Getting Guard context ready…"})
            payload = await _execute_chat(req, workspace_id, db, emit=emit)
            answer = str(payload.get("answer") or "")
            if answer:
                for chunk in answer.split(" "):
                    emit("answer_delta", {"delta": f"{chunk} "})
                    await asyncio.sleep(0.01)
            emit("final", payload)
        except HTTPException as exc:
            emit("error", {"error": str(exc.detail)})
        except Exception:
            emit("error", {"error": "Inference unavailable — model may be cold, retry in 30s"})
        finally:
            emit("done", {})

    task = asyncio.create_task(worker())

    async def event_stream():
        try:
            while True:
                event, payload = await queue.get()
                yield _format_sse(event, payload)
                if event == "done":
                    break
        finally:
            await task

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/opener")
def glens_opener(
    page_context: str | None = Query(default=None),
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    executor = Executor(db, workspace_id)
    governance = _safe_json_loads(executor.call("get_governance_kpis", "{}"), {}) or {}
    compliance = _safe_json_loads(executor.call("get_compliance_status", "{}"), {}) or {}
    blocked = governance.get("blocked_today", 0)
    events = governance.get("events_today", 0)
    grade = compliance.get("grade", "unknown")
    answer = (
        f"Hi. You have {blocked} blocked events out of {events} Guard events today, "
        f"and your governance grade is {grade}. Want me to show what changed?"
    )
    followups = _default_followups("governance", page_context or "governance")
    return {
        "skill": "governance",
        "answer": answer,
        "followups": followups,
        "attachments": [],
        "page_context": page_context,
    }


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
    action: str
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
        if pattern := req.draft.get("match_pattern"):
            try:
                re.compile(pattern)
            except re.error as e:
                raise HTTPException(status_code=400, detail=f"Invalid match_pattern regex: {e}")
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

    if req.action == "patch":
        rule_id = req.target_rule_id
        if not rule_id:
            raise HTTPException(status_code=400, detail="target_rule_id is required for patch")
        rule = db.query(WorkspaceCustomRule).filter(
            WorkspaceCustomRule.workspace_id == ws_uuid,
            WorkspaceCustomRule.rule_id == rule_id,
        ).first()
        if not rule:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
        if pattern := req.draft.get("match_pattern"):
            try:
                re.compile(pattern)
            except re.error as e:
                raise HTTPException(status_code=400, detail=f"Invalid match_pattern regex: {e}")
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


class GuardConfigApplyRequest(BaseModel):
    draft: dict


_VALID_ENFORCEMENT = {"active", "warn", "advisory", "off"}
_VALID_FAIL_MODE = {"fail_open", "fail_closed"}


@router.post("/guard_config/apply", status_code=200)
def guard_config_apply(
    req: GuardConfigApplyRequest,
    _: str = Depends(require_permission("guard.settings.edit")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = _parse_workspace_id(workspace_id)
    cfg = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Guard not configured for this workspace")
    if "enforcement_mode" in req.draft:
        val = req.draft["enforcement_mode"]
        if val not in _VALID_ENFORCEMENT:
            raise HTTPException(status_code=400, detail=f"enforcement_mode must be one of: {', '.join(sorted(_VALID_ENFORCEMENT))}")
        cfg.enforcement_mode = val
    if "fail_mode" in req.draft:
        val = req.draft["fail_mode"]
        if val not in _VALID_FAIL_MODE:
            raise HTTPException(status_code=400, detail="fail_mode must be 'fail_open' or 'fail_closed'")
        cfg.fail_mode = val
    for bool_field in ("advisory_mode", "notify_on_block", "notify_on_budget", "deny_on_error"):
        if bool_field in req.draft:
            setattr(cfg, bool_field, bool(req.draft[bool_field]))
    cfg.updated_at = datetime.now(timezone.utc)
    db.commit()
    log.info("glens.guard_config.patched", workspace_id=workspace_id)
    return {"ok": True, "action": "patched"}


class SpendConfigApplyRequest(BaseModel):
    monthly_limit_usd: float
    hard_limit_usd: float | None = None
    alert_threshold_pct: int = 80
    email: str | None = None


@router.post("/spend_config/apply", status_code=201)
def spend_config_apply(
    req: SpendConfigApplyRequest,
    _: str = Depends(require_permission("guard.spend.budgets.edit")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    from app.modules.guard.models import GuardSession as _GuardSession
    ws_uuid = _parse_workspace_id(workspace_id)

    clerk_user_id: str | None = None
    if req.email:
        session_row = (
            db.query(_GuardSession)
            .filter(
                _GuardSession.workspace_id == ws_uuid,
                _GuardSession.user_email == req.email,
                _GuardSession.clerk_user_id.isnot(None),
            )
            .order_by(_GuardSession.started_at.desc())
            .first()
        )
        if not session_row:
            raise HTTPException(status_code=404, detail=f"No Guard sessions found for {req.email} — cannot resolve to Clerk user ID")
        clerk_user_id = session_row.clerk_user_id

    existing = db.query(GuardSpendBudget).filter(
        GuardSpendBudget.workspace_id == ws_uuid,
        GuardSpendBudget.clerk_user_id == clerk_user_id,
    ).first()
    now = datetime.now(timezone.utc)
    if existing:
        existing.monthly_limit_usd = req.monthly_limit_usd
        existing.hard_limit_usd = req.hard_limit_usd
        existing.alert_threshold_pct = req.alert_threshold_pct
        existing.updated_at = now
        db.commit()
        action = "updated"
    else:
        db.add(GuardSpendBudget(
            workspace_id=ws_uuid,
            clerk_user_id=clerk_user_id,
            monthly_limit_usd=req.monthly_limit_usd,
            hard_limit_usd=req.hard_limit_usd,
            alert_threshold_pct=req.alert_threshold_pct,
        ))
        db.commit()
        action = "created"
    scope = "workspace" if req.email is None else f"developer:{req.email}"
    log.info("glens.spend_config.applied", workspace_id=workspace_id, scope=scope, action=action)
    return {"ok": True, "action": action, "scope": scope}


@router.get("/sessions/{session_id}")
def get_session(
    session_id: str,
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = _parse_workspace_id(workspace_id)
    session = _get_session(db, session_id, ws_uuid)
    messages = _safe_json_loads(session.messages, []) or []
    user_messages = [m for m in messages if m.get("role") != "system"]
    return {
        "id": str(session.id),
        "title": session.title,
        "messages": user_messages,
        "spec": _safe_json_loads(session.render_spec, None),
        "context_summary": session.context_summary,
        "created_at": session.created_at.isoformat(),
    }
