"""
POST /glens/chat/stream  — GLens governance assistant (tool-use + prose)
GET  /glens/sessions     — list sessions
GET  /glens/sessions/{id} — restore session
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.models.workspace_config import WorkspaceConfig
from app.modules.glens.executor import Executor
from app.modules.glens.models import GlensChatSession
from app.modules.guard.models import GuardConfig, GuardSpendBudget, WorkspaceCustomRule

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/glens", tags=["glens"])


# ── Tools exposed to the LLM ─────────────────────────────────────────────────

TOOLS = [
    {
        "name": "get_event_count",
        "description": "Count Guard audit events. Use for 'how many blocks/warnings/allows' questions. Returns a single integer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["blocked", "warned", "allowed"], "description": "Filter by decision type"},
                "since": {"type": "string", "description": "ISO date start, e.g. 2026-07-01"},
                "until": {"type": "string", "description": "ISO date end, e.g. 2026-07-31T23:59:59"},
                "rule_id": {"type": "string", "description": "Filter by specific rule ID"},
            },
        },
    },
    {
        "name": "get_recent_events",
        "description": (
            "Fetch recent Guard audit events with details (who, what tool, which rule, decision, timestamp). "
            "Use for 'what happened', 'who got blocked', 'show recent activity'. "
            "Keep limit<=10 unless user explicitly asks for more."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 5, "description": "Max events (max 20)"},
                "decision": {"type": "string", "enum": ["blocked", "warned", "allowed"]},
                "since": {"type": "string", "description": "ISO date start"},
                "until": {"type": "string", "description": "ISO date end"},
                "rule_id": {"type": "string"},
            },
        },
    },
    {
        "name": "get_spend_summary",
        "description": "Get AI spend/cost summary: total cost, events today, active developers, tokens saved, cost by tool and developer.",
        "input_schema": {
            "type": "object",
            "properties": {
                "month": {"type": "string", "description": "YYYY-MM, defaults to current month"},
            },
        },
    },
    {
        "name": "list_policies",
        "description": "List all Guard policies/rules configured for this workspace.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_governance_kpis",
        "description": "Get high-level governance KPIs: blocks today, warnings today, events today, active developers, blocks month-to-date.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_savings_summary",
        "description": "Get token and cost savings from Guard enforcement: tokens blocked, estimated cost saved.",
        "input_schema": {"type": "object", "properties": {}},
    },
]

_SYSTEM = """\
You are GLens, a governance assistant for ConductAI Guard.
Today is {today}.

Answer questions about AI governance data in clear, direct prose. Be specific and use exact numbers.
- 2-4 sentences for simple questions; a short paragraph for summaries
- Always call the right tool first — do not guess numbers
- For count questions, also call get_recent_events (limit=5) to identify top offenders/rules/patterns
- Include trend context when relevant: compare to previous period if data suggests it
- Name the top 1-2 items (e.g. "mostly from the no-pii rule" or "primarily hitting user@example.com")
- Never dump raw data or show tables — synthesize into a human answer
- When asked to "show all" or list more than 10 records, just give the count — a link to the full list will be added automatically
- Never construct or include URLs in your response
"""


# ── LLM client factory ────────────────────────────────────────────────────────

def _llm_client(db=None, workspace_id: str | None = None):
    from app.runtime.llm_client import client_for
    from app.core.config import settings
    provider = settings.conduct_inference_provider or "openai"
    endpoint = (settings.conduct_inference_endpoint_url or "").rstrip("/")
    if endpoint and endpoint.endswith("/v1"):
        endpoint = endpoint[:-3]
    api_key = settings.conduct_inference_token_id or (
        settings.openai_api_key if provider == "openai" else ""
    ) or "unused"
    if db and workspace_id:
        try:
            from app.modules.credentials.vault import get_credential
            creds = get_credential(db, workspace_id, provider)
            api_key = creds.get("api_key") or api_key
        except Exception:
            pass
    return client_for(provider, api_key=api_key, base_url=endpoint or None)


# ── Core tool loop ────────────────────────────────────────────────────────────

def _build_drilldown(tool_calls: list[tuple[str, dict]]) -> str | None:
    """Build a grounded drilldown URL from the tool calls the LLM actually made."""
    page = "/guard/activity"
    filters: dict[str, str] = {}

    for name, args in tool_calls:
        if name in ("get_event_count", "get_recent_events"):
            if args.get("decision"):
                filters["decision"] = args["decision"]
            if args.get("since"):
                filters["since"] = args["since"]
            if args.get("until"):
                filters["until"] = args["until"]
            if args.get("rule_id"):
                filters["rule_id"] = args["rule_id"]
        elif name == "get_spend_summary":
            page = "/guard/spend"
        elif name == "list_policies":
            page = "/guard/policies"
        elif name == "get_savings_summary":
            page = "/guard/spend"

    if not filters and page == "/guard/activity":
        return None
    if filters:
        qs = "&".join(f"{k}={v}" for k, v in filters.items())
        return f"{page}?{qs}"
    return page


def _resolve_tools(messages: list[dict], system: str, executor: Executor) -> tuple[list[dict], str | None, list[tuple[str, dict]]]:
    """Phase 1: Execute tool calls. Returns (final_msgs, early_text, tool_calls_made)."""
    from app.runtime.llm_client import LLMToolUseBlock
    from app.core.config import settings as _s

    provider = _s.conduct_inference_provider or "openai"
    model = _s.conduct_inference_model_name or "gpt-4o-mini"
    endpoint = (_s.conduct_inference_endpoint_url or "").rstrip("/") or "(default)"
    log.info("glens.llm_call", provider=provider, model=model, endpoint=endpoint)
    client = _llm_client(executor.db, executor.workspace_id)
    msgs = list(messages)
    tool_calls_made: list[tuple[str, dict]] = []

    for _ in range(5):
        resp = client.create(model=model, messages=msgs, system=system, tools=TOOLS, max_tokens=512)
        tool_blocks = [b for b in resp.content if isinstance(b, LLMToolUseBlock)]
        text = next((b.text for b in resp.content if hasattr(b, "text") and b.text), "")

        if not tool_blocks:
            return msgs, text or "I couldn't find relevant data to answer that.", tool_calls_made

        msgs.extend(client.make_assistant_turn(resp))
        results = []
        for block in tool_blocks:
            tool_calls_made.append((block.name, block.input))
            result = executor.call(block.name, json.dumps(block.input))
            log.debug("glens.tool", name=block.name, result_len=len(result))
            results.append((block.id, result))
        msgs.extend(client.make_tool_results_turn(results))

    return msgs, None, tool_calls_made


def _stream_synthesis(msgs: list[dict], system: str, executor: Executor, on_token) -> str:
    """Phase 2: Stream the final synthesis response, calling on_token for each chunk."""
    import httpx
    from app.core.config import settings as _s

    model = _s.conduct_inference_model_name or "gpt-4o-mini"
    endpoint = (_s.conduct_inference_endpoint_url or "").rstrip("/")
    if endpoint and endpoint.endswith("/v1"):
        endpoint = endpoint[:-3]
    base_url = endpoint or "https://api.openai.com"
    api_key = _s.conduct_inference_token_id or _s.openai_api_key or "unused"

    if executor.db and executor.workspace_id:
        try:
            from app.modules.credentials.vault import get_credential
            provider = _s.conduct_inference_provider or "openai"
            creds = get_credential(executor.db, executor.workspace_id, provider)
            api_key = creds.get("api_key") or api_key
        except Exception:
            pass

    oai_msgs = [{"role": "system", "content": system}] + msgs
    payload = {"model": model, "messages": oai_msgs, "max_tokens": 1024, "stream": True}

    full_text = ""
    with httpx.stream(
        "POST", f"{base_url}/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    ) as r:
        if r.status_code >= 400:
            body = r.read().decode()[:500]
            raise Exception(f"OpenAI stream {r.status_code}: {body}")
        for line in r.iter_lines():
            if not line or line == "data: [DONE]":
                continue
            if line.startswith("data: "):
                try:
                    chunk = json.loads(line[6:])
                    token = ((chunk.get("choices") or [{}])[0]).get("delta", {}).get("content") or ""
                    if token:
                        full_text += token
                        on_token(token)
                except Exception:
                    pass
    return full_text or "Could not complete the analysis."


# ── Session helpers ───────────────────────────────────────────────────────────

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


def _should_refresh_summary(messages: list[dict]) -> bool:
    user_count = sum(1 for m in messages if m.get("role") == "user")
    return user_count % 5 == 0 and len(messages) > 10


def _bg_save_session(session_id: str, messages: list[dict], title: str | None) -> None:
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        sess = db.query(GlensChatSession).filter(GlensChatSession.id == uuid.UUID(session_id)).first()
        if sess:
            sess.messages = json.dumps(messages)
            if title:
                sess.title = title[:60]
            sess.updated_at = datetime.now(timezone.utc)
            db.commit()
    except Exception as exc:
        log.warning("glens.session.save_failed", session_id=session_id, error=str(exc))
    finally:
        db.close()


def _build_llm_messages(session_messages: list[dict]) -> list[dict]:
    """Extract clean user/assistant turns for LLM context (last 20)."""
    result = []
    for m in session_messages:
        if m["role"] == "system":
            continue
        if m["role"] == "assistant":
            try:
                content = json.loads(m["content"]).get("answer", m["content"])
            except Exception:
                content = m["content"]
            result.append({"role": "assistant", "content": content})
        else:
            result.append({"role": m["role"], "content": m["content"]})
    return result[-20:]


# ── Chat stream ───────────────────────────────────────────────────────────────

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

    session = None
    if req.session_id:
        session = _get_session(db, req.session_id, ws_uuid)
    if not session:
        session = GlensChatSession(workspace_id=ws_uuid, title=req.message[:60], messages=json.dumps([]))
        db.add(session)
        db.flush()
        db.commit()

    session_messages = json.loads(session.messages)
    session_messages.append({"role": "user", "content": req.message})
    session_id_str = str(session.id)
    executor = Executor(db, workspace_id)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    system = _SYSTEM.format(today=today)
    llm_messages = _build_llm_messages(session_messages)

    loop = asyncio.get_running_loop()
    event_q: asyncio.Queue[dict] = asyncio.Queue()

    async def _run_work() -> None:
        try:
            # Phase 1: resolve tool calls (fast, non-streaming)
            final_msgs, early_text, tool_calls = await asyncio.to_thread(_resolve_tools, llm_messages, system, executor)
            drilldown = _build_drilldown(tool_calls)

            if early_text:
                answer = early_text
                if drilldown:
                    answer += f"\n\n[View all →]({drilldown})"
                for char in answer:
                    await event_q.put({"type": "token", "text": char})
                    await asyncio.sleep(0)
                await event_q.put({"type": "done", "answer": answer})
                return

            # Phase 2: stream synthesis (tools already resolved)
            def on_token(t: str):
                loop.call_soon_threadsafe(event_q.put_nowait, {"type": "token", "text": t})

            answer = await asyncio.to_thread(_stream_synthesis, final_msgs, system, executor, on_token)
            if drilldown:
                link = f"\n\n[View all →]({drilldown})"
                for char in link:
                    await event_q.put({"type": "token", "text": char})
                    await asyncio.sleep(0)
                answer += link
            await event_q.put({"type": "done", "answer": answer})
        except Exception as e:
            logger.error("glens.stream.failed", error=str(e))
            await event_q.put({"type": "error", "message": "Something went wrong. Please try again."})

    async def generate():
        task = asyncio.create_task(_run_work())
        yield f"data: {json.dumps({'type': 'thinking', 'label': 'Checking your governance data...'})}\n\n"
        try:
            while True:
                evt = await asyncio.wait_for(event_q.get(), timeout=60)

                if evt.get("type") == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': evt['message']})}\n\n"
                    break

                elif evt.get("type") == "token":
                    yield f"data: {json.dumps({'type': 'token', 'text': evt['text']})}\n\n"

                elif evt.get("type") == "done":
                    answer = evt["answer"]
                    session_messages.append({
                        "role": "assistant",
                        "content": json.dumps({"answer": answer, "skill": "governance"}),
                    })
                    capped = session_messages[-50:]
                    background_tasks.add_task(_bg_save_session, session_id_str, capped, None)

                    yield f"data: {json.dumps({'type': 'done', 'session_id': session_id_str, 'skill': 'governance', 'answer': answer})}\n\n"
                    break
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Request timed out. Please try again.'})}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Session CRUD ──────────────────────────────────────────────────────────────

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
        SessionOut(id=str(s.id), title=s.title, created_at=s.created_at.isoformat(), has_dashboard=False)
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
    user_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in messages if m["role"] != "system"
    ]
    return {
        "id": str(session.id),
        "title": session.title,
        "messages": user_messages,
        "spec": None,
        "created_at": session.created_at.isoformat(),
    }


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


# ── GLens install / status ────────────────────────────────────────────────────

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
    return {"installed": False}


# ── Policy / config / spend apply endpoints ───────────────────────────────────

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
        return {"ok": True, "rule_id": rule_id, "action": "created"}

    elif req.action == "patch":
        from app.modules.guard.routers.policies import _upsert_override
        rule_id = req.target_rule_id
        if not rule_id:
            raise HTTPException(status_code=400, detail="target_rule_id is required for patch")
        if pattern := req.draft.get("match_pattern"):
            import re
            try:
                re.compile(pattern)
            except re.error as e:
                raise HTTPException(status_code=400, detail=f"Invalid match_pattern regex: {e}")
        custom = db.query(WorkspaceCustomRule).filter(
            WorkspaceCustomRule.workspace_id == ws_uuid,
            WorkspaceCustomRule.rule_id == rule_id,
        ).first()
        if custom:
            if "enabled" in req.draft:
                custom.enabled = req.draft["enabled"]
            body_patch = {k: v for k, v in req.draft.items() if k != "enabled"}
            if body_patch:
                custom.body = {**custom.body, **body_patch}
            custom.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {"ok": True, "rule_id": rule_id, "action": "patched"}
        touched = False
        if "enabled" in req.draft:
            _upsert_override(db, ws_uuid, rule_id, disabled=not req.draft["enabled"])
            touched = True
        action_val = req.draft.get("action")
        msg_val = req.draft.get("message")
        pat_val = req.draft.get("match_pattern")
        if action_val or msg_val or pat_val:
            _upsert_override(db, ws_uuid, rule_id, action=action_val, message=msg_val, match_pattern=pat_val)
            touched = True
        if not touched:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
        db.commit()
        return {"ok": True, "rule_id": rule_id, "action": "patched"}

    elif req.action == "delete":
        rule_id = req.target_rule_id or req.draft.get("rule_id")
        if not rule_id:
            raise HTTPException(status_code=400, detail="target_rule_id is required for delete")
        rule = db.query(WorkspaceCustomRule).filter(
            WorkspaceCustomRule.workspace_id == ws_uuid,
            WorkspaceCustomRule.rule_id == rule_id,
        ).first()
        if not rule:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
        db.delete(rule)
        db.commit()
        return {"ok": True, "rule_id": rule_id, "action": "deleted"}

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
            raise HTTPException(status_code=404, detail=f"No Guard sessions found for {req.email}")
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
    return {"ok": True, "action": action, "scope": scope}
