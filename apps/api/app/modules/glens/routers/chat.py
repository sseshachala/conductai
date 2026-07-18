"""
POST /glens/chat/stream     — conversational governance reporting (SSE)
GET  /glens/sessions        — list persisted chat sessions
GET  /glens/sessions/{id}   — restore a session
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, BaseModel as _Base
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.models.workspace_config import WorkspaceConfig
from app.modules.glens.agent import Agent
from app.modules.glens.coordinator import coordinate
from app.modules.glens.executor import Executor
from app.modules.glens.formatters import format_tool_result
from app.modules.glens.inference import dispatch_tool
from app.modules.glens.planner import plan
from app.modules.glens.shortcuts import try_shortcut
from app.modules.glens.utils import extract_json
from app.modules.glens.models import GlensChatSession
from app.modules.glens.prompts import KPI_META, CHART_META, TABLE_META, VALID_KPIS, VALID_CHARTS, VALID_TABLES
from app.modules.guard.models import GuardConfig, GuardSpendBudget, WorkspaceCustomRule

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/glens", tags=["glens"])


# ── Tier 2: catalog phrase matching ──────────────────────────────────────────

def _load_catalog() -> dict:
    import yaml
    from pathlib import Path
    path = Path(__file__).parent.parent / "catalog.yaml"
    try:
        return yaml.safe_load(path.read_text()).get("actions", {})
    except Exception:
        return {}

_CATALOG: dict = {}

def _get_catalog() -> dict:
    global _CATALOG
    if not _CATALOG:
        _CATALOG = _load_catalog()
    return _CATALOG

def _tier2_match(message: str) -> str | None:
    """Match message against catalog action phrases. Returns action name or None."""
    low = message.lower()
    catalog = _get_catalog()
    for action_name, action in catalog.items():
        for phrase in action.get("phrases", []):
            if phrase.lower() in low:
                return action_name
    return None


# ---------------------------------------------------------------------------
# Pydantic models for sanitizing model JSON output
# ---------------------------------------------------------------------------

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
    # stat-row
    items: list[_StatItem | _BadgeItem] | None = None
    # table
    columns: list[_Column] | None = None
    rows: list[dict[str, Any]] | None = None
    # bar-chart
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
            continue  # skip malformed blocks silently
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
    # rows are free-form dicts — just ensure each element is a dict
    return [r for r in raw if isinstance(r, dict)] or None


def _should_refresh_summary(messages: list[dict]) -> bool:
    user_count = sum(1 for m in messages if m.get("role") == "user")
    return user_count % 5 == 0 and len(messages) > 10


def _conversation_messages(messages: list[dict], window: int = 20) -> list[dict]:
    """Return the last `window` messages for model context, excluding system turns."""
    return [m for m in messages if m.get("role") != "system"][-window:]


def _summarize_messages(messages: list[dict], prior_summary: str | None) -> str:
    """Produce a short summary of the conversation so far."""
    from app.modules.glens.inference import chat as qwen_chat

    user_turns = [m["content"] for m in messages if m.get("role") == "user"][-10:]
    prior = f"Prior summary: {prior_summary}\n\n" if prior_summary else ""
    prompt = (
        f"{prior}Summarize the following conversation in 2-3 sentences, focusing on "
        f"what data the user asked about and any key findings:\n\n"
        + "\n".join(f"- {t}" for t in user_turns)
    )
    try:
        return qwen_chat([
            {"role": "system", "content": "You are a concise summarizer. Reply with plain text only."},
            {"role": "user", "content": prompt},
        ])
    except Exception:
        return prior_summary or ""


def _bg_save_session(
    session_id: str,
    messages: list[dict],
    spec: dict | None,
    title: str | None,
    prior_summary: str | None,
) -> None:
    """Persist messages + spec on a fresh DB session to avoid thread-safety issues."""
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        sess = db.query(GlensChatSession).filter(GlensChatSession.id == uuid.UUID(session_id)).first()
        if sess:
            sess.messages = json.dumps(messages)
            if spec:
                sess.render_spec = json.dumps(spec)
            if title:
                sess.title = title[:60]
            sess.updated_at = datetime.now(timezone.utc)
            db.commit()
            if _should_refresh_summary(messages):
                sess.context_summary = _summarize_messages(messages, prior_summary)
                sess.updated_at = datetime.now(timezone.utc)
                db.commit()
    except Exception as exc:
        log.warning("glens.stream.save_failed", session_id=session_id, error=str(exc))
    finally:
        db.close()


def _bg_refresh_summary(session_id: str, messages: list[dict], prior_summary: str | None) -> None:
    from app.core.database import SessionLocal

    db = SessionLocal()
    try:
        sess = db.query(GlensChatSession).filter(GlensChatSession.id == uuid.UUID(session_id)).first()
        if sess:
            sess.context_summary = _summarize_messages(messages, prior_summary)
            sess.updated_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:
        log.warning("glens.summary.bg_failed", session_id=session_id, error=str(exc))
    finally:
        db.close()


def _normalize_payload(parsed: dict) -> dict:
    """Ensure consistent shape regardless of which skill produced the result."""
    # Resolve spec blocks from nested structure if present
    if "spec" in parsed and isinstance(parsed["spec"], dict):
        spec = parsed["spec"]
        if "blocks" in spec and "blocks" not in parsed:
            parsed["blocks"] = spec["blocks"]

    # Ensure followups is always a list
    if "followups" not in parsed or not isinstance(parsed.get("followups"), list):
        parsed["followups"] = _default_followups(parsed.get("skill", ""))

    return parsed


def _default_followups(skill: str) -> list[str]:
    defaults: dict[str, list[str]] = {
        "analytics": ["Show me this week's trend", "Which developer spent the most?", "Export this as CSV"],
        "governance": ["Who triggered the most blocks?", "Show me today's events", "Which rules fired most?"],
        "rules": ["Show all active rules", "Create a new block rule", "Which rules fired this week?"],
        "discovery": ["Which agents are not under Guard?", "Show coverage by framework", "What's our risk score?"],
        "compliance": ["What's our governance grade?", "Show OWASP Agentic Top 10 status", "Which controls are failing?"],
        "memory": ["What decisions were made last week?", "Search for policy context", "Show recent team decisions"],
        "session": ["Show sessions from yesterday", "Which agents ran the longest?", "Find high-autonomy sessions"],
        "extract": ["Export blocked events", "Download spend summary", "Export audit log as CSV"],
    }
    return defaults.get(skill, ["Show me an overview", "What happened today?", "Export this data"])


def _build_answer(parsed: dict, spec: dict | None) -> str:
    """Extract the best answer string from a parsed payload."""
    if parsed.get("answer"):
        return parsed["answer"]
    if parsed.get("question"):
        return parsed["question"]
    if spec:
        return f"Here is your {parsed.get('title', 'report')}."
    return "I couldn't generate an answer. Please try rephrasing your question."


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
    page_context: str | None = None


class SessionOut(BaseModel):
    id: str
    title: str
    created_at: str
    has_dashboard: bool


@router.post("/chat/stream")
async def glens_chat_stream(
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = _parse_workspace_id(workspace_id)
    logger = log.bind(workspace_id=workspace_id)

    # Load or create session using the request-scoped db, then commit immediately
    # so the session row is durable before any streaming/thread work touches the db.
    session = None
    if req.session_id:
        session = _get_session(db, req.session_id, ws_uuid)
    if not session:
        session = GlensChatSession(workspace_id=ws_uuid, title=req.message[:60], messages=json.dumps([]))
        db.add(session)
        db.flush()
        db.commit()  # commit now — threads will use same db but session row is safe

    messages = json.loads(session.messages)
    messages.append({"role": "user", "content": req.message})

    last_answer: str | None = None
    prior = [m for m in messages[:-1] if m["role"] == "assistant"]
    if prior:
        try:
            last_answer = json.loads(prior[-1]["content"]).get("answer", "")[:300]
        except Exception:
            pass

    context_summary = session.context_summary if hasattr(session, "context_summary") else None
    executor = Executor(db, workspace_id)
    session_id_str = str(session.id)
    loop = asyncio.get_running_loop()
    event_q: asyncio.Queue[dict] = asyncio.Queue()

    def _on_event(evt: dict) -> None:
        loop.call_soon_threadsafe(event_q.put_nowait, evt)

    async def _run_work() -> None:
        try:
            # Tier 1: shortcut — deterministic regex, no LLM (<1ms)
            shortcut = await asyncio.to_thread(try_shortcut, req.message, executor)
            if shortcut:
                log.debug("glens.stream.tier1_hit", message=req.message[:60])
                await event_q.put({"type": "done", "_parsed": shortcut})
                return

            # Tier 2: catalog phrase match — keyword match against action phrases, no LLM
            action_name = await asyncio.to_thread(_tier2_match, req.message)
            if action_name:
                log.debug("glens.stream.tier2_hit", action=action_name)
                _on_event({"type": "thinking", "label": f"Looking up {action_name.replace('_', ' ')}..."})
                raw = await asyncio.to_thread(executor.call, action_name.replace("view_", "get_"), "{}")
                import json as _json
                result = _json.loads(raw)
                formatted = format_tool_result(action_name, result)
                if formatted:
                    await event_q.put({"type": "done", "_parsed": formatted})
                    return

            # Tier 3: 1 LLM call — dispatch picks tool + args, Python formats result
            try:
                tool_name, args = await asyncio.to_thread(dispatch_tool, req.message)
                import json as _json
                _on_event({"type": "thinking", "label": f"Running {tool_name.replace('_', ' ')}..."})
                raw = await asyncio.to_thread(executor.call, tool_name, _json.dumps(args))
                result = _json.loads(raw)
                formatted = format_tool_result(tool_name, result)
                if formatted:
                    log.debug("glens.stream.tier3_hit", tool=tool_name)
                    await event_q.put({"type": "done", "_parsed": formatted})
                    return
            except Exception as e:
                log.debug("glens.stream.tier3_miss", error=str(e))

            # Tier 4: full agent loop — escalation path for complex/multi-domain queries
            log.debug("glens.stream.tier4_escalate", message=req.message[:60])
            subtasks = await asyncio.to_thread(
                plan, req.message, last_answer, req.page_context, context_summary
            )
            results = []
            for subtask in subtasks:
                skill = subtask.get("skill", "report")
                agent = Agent([skill])
                sub_msgs = _conversation_messages(messages)
                if len(subtasks) > 1:
                    sub_msgs = sub_msgs[:-1] + [{"role": "user", "content": subtask["question"]}]
                result = await asyncio.to_thread(agent.run, sub_msgs, executor, _on_event)
                results.append(result)
            parsed = coordinate(results)
            await event_q.put({"type": "done", "_parsed": parsed})
        except Exception as e:
            logger.error("glens.stream.failed", error=str(e))
            await event_q.put({"type": "error", "message": "Inference unavailable — model may be cold, retry in 30s"})

    async def generate():
        task = asyncio.create_task(_run_work())
        try:
            while True:
                evt = await asyncio.wait_for(event_q.get(), timeout=120)

                if evt.get("type") == "thinking":
                    yield f"data: {json.dumps({'type': 'thinking', 'label': evt.get('label', '')})}\n\n"

                elif evt.get("type") == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': evt['message']})}\n\n"
                    break

                elif evt.get("type") == "done":
                    parsed = _normalize_payload(evt["_parsed"])

                    messages.append({
                        "role": "assistant",
                        "content": json.dumps(parsed),
                        "rendered": {"page_kind": parsed.get("page_kind"), "blocks": parsed.get("blocks"), "rows": parsed.get("rows")},
                    })
                    capped = messages[-50:] if len(messages) > 50 else messages

                    spec = None
                    if parsed.get("ready"):
                        spec = parsed.get("spec") or _build_spec(
                            title=parsed.get("title", "Guard Overview"),
                            month=parsed.get("month", ""),
                            kpi_picks=parsed.get("kpis", []),
                            chart_picks=parsed.get("charts", []),
                            table_picks=parsed.get("tables", []),
                        )

                    # Fresh SessionLocal — avoids thread-safety issues with request-scoped db
                    _bg_save_session(session_id_str, capped, spec, parsed.get("title"), context_summary)

                    page_kind = parsed.get("page_kind")
                    page_data = parsed.get("data")
                    if page_kind and (page_data is None or not isinstance(page_data, dict)):
                        page_kind = None
                        page_data = None

                    payload = {
                        "type": "done",
                        "session_id": session_id_str,
                        "skill": parsed.get("skill", "report"),
                        "ready": spec is not None,
                        "answer": _build_answer(parsed, spec),
                        "spec": spec,
                        "page_kind": page_kind,
                        "page_data": page_data,
                        "blocks":   _sanitize_blocks(parsed.get("blocks")),
                        "rows":     _sanitize_rows(parsed.get("rows")),
                        "columns":  _sanitize_columns(parsed.get("columns")),
                        "warning":  parsed.get("warning"),
                        "followups": parsed.get("followups"),
                        "confirm_required": parsed.get("confirm_required"),
                        "action": parsed.get("action"),
                        "draft": parsed.get("draft"),
                        "mapping": parsed.get("mapping", []),
                        "target_rule_id": parsed.get("target_rule_id"),
                    }
                    logger.info("glens.stream.complete", skill=payload["skill"])
                    yield f"data: {json.dumps(payload)}\n\n"
                    break

        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Request timed out'})}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _build_spec(title: str, month: str, kpi_picks: list, chart_picks: list, table_picks: list) -> dict:
    """Assemble spec from model's validated picks — model selects, backend wires."""
    spend_ep = f"/guard/spend{f'?month={month}' if month else ''}"

    kpis = [
        {**KPI_META[k], "endpoint": spend_ep}
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
            {"label": "Events Today",  "endpoint": spend_ep, "field": "events_today"},
            {"label": "Blocks Today",  "endpoint": spend_ep, "field": "blocked_today",      "color": "err"},
            {"label": "Total Cost",    "endpoint": spend_ep, "field": "total_cost_usd"},
            {"label": "Active Devs",   "endpoint": spend_ep, "field": "active_developers"},
        ]

    return {"title": title, "kpis": kpis, "charts": charts, "tables": tables}


_GLENS_KEY = "glens_enabled"


def _glens_row(db: Session, ws_uuid: uuid.UUID):
    return db.query(WorkspaceConfig).filter(
        WorkspaceConfig.workspace_id == ws_uuid,
        WorkspaceConfig.key == _GLENS_KEY,
    ).first()


@router.get("/opener")
def glens_opener(
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    """Return 4 data-grounded suggestion chips for the empty-state screen."""
    executor = Executor(db, workspace_id)
    try:
        kpis = executor._tool_get_governance_kpis()
    except Exception:
        kpis = {}

    blocked = kpis.get("blocked_today", 0)
    events = kpis.get("events_today", 0)
    blocks_mtd = kpis.get("blocks_mtd", 0)
    devs = kpis.get("active_developers_today", 0)

    chips: list[str] = []

    if blocked > 0:
        chips.append(f"Who was blocked today? ({blocked} block{'s' if blocked != 1 else ''})")
    else:
        chips.append("Show me today's Guard activity")

    if events > 0:
        chips.append(f"Show the most recent events today ({events} total)")
    else:
        chips.append("Show recent Guard events")

    if blocks_mtd > 0:
        chips.append(f"How many blocks this month? ({blocks_mtd} so far)")
    else:
        chips.append("Cost by AI tool this month")

    if devs > 1:
        chips.append(f"Who are the {devs} active developers today?")
    else:
        chips.append("Which rule triggered most this week?")

    return {"chips": chips}


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
        if pattern := req.draft.get("match_pattern"):
            import re
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
        if pattern := req.draft.get("match_pattern"):
            import re
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
    email: str | None = None            # None = workspace-wide


@router.post("/spend_config/apply", status_code=201)
def spend_config_apply(
    req: SpendConfigApplyRequest,
    _: str = Depends(require_permission("guard.spend.budgets.edit")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    from app.modules.guard.models import GuardSession as _GuardSession
    ws_uuid = _parse_workspace_id(workspace_id)

    # Resolve email → clerk_user_id so enforcement can match at hook time
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

    messages = json.loads(session.messages)
    user_messages = []
    for m in messages:
        if m["role"] == "system":
            continue
        entry: dict = {"role": m["role"], "content": m["content"]}
        if m.get("rendered"):
            entry["rendered"] = m["rendered"]
        user_messages.append(entry)

    return {
        "id": str(session.id),
        "title": session.title,
        "messages": user_messages,
        "spec": json.loads(session.render_spec) if session.render_spec else None,
        "created_at": session.created_at.isoformat(),
    }
