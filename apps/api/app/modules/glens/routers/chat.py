"""
POST /glens/chat/stream  — GLens governance assistant (tool-use + prose)

Sessions / feedback / opener / policy / config / guard_config / spend_config
live in sibling router modules (#1459 split). Helpers used across those
files sit in `_helpers.py`.
"""
import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.glens.executor import Executor
from app.modules.glens.entry_context import LensEntryContext, resolve_entry_context
from app.modules.glens.masking import mask_secrets
from app.modules.glens.models import GlensChatSession
from app.tools import registrations as _tool_registrations  # noqa: F401  # side-effect: populate default_registry before TOOLS derives

from ._helpers import _get_session, _parse_workspace_id
from app.modules.glens.routers.chat_tools import (
    TOOLS,
    _SYSTEM,
)

# Re-exported for callers that import these names from this module.
from app.modules.glens.routers.chat_tools import (  # noqa: E402,F401
    _LEGACY_DESCRIPTIONS,
)

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/glens", tags=["glens"])


# ── LLM config resolution (PR C of #1347) ─────────────────────────────────────

def _llm_config(executor):
    """Resolve (client, provider, model) for a Lens session from the workspace
    primitives (issue #1347) and the workspace vault.

    - provider + model come from workspace_llm_primitives; falls back to
      seeded defaults if the workspace has no row yet.
    - api_key is looked up in the workspace vault by provider handle;
      missing or unreadable credentials stop before a provider request.
    """
    from app.runtime.model_router import resolve_for_workspace
    from app.runtime.llm_client import client_for
    from app.core.credentials import get_credential
    from app.modules.glens.vault_settings import selected_environment

    provider, model, reason = resolve_for_workspace(
        db=executor.db,
        workspace_id=executor.workspace_id,
        routing_preference="balanced",
    )

    api_key = None
    environment_id = selected_environment(executor.db, executor.workspace_id)
    if executor.db and executor.workspace_id:
        try:
            creds = get_credential(executor.db, executor.workspace_id, provider, environment_id=environment_id)
            api_key = creds.get("api_key")
        except Exception:
            raise ValueError(
                f"Lens could not read the {provider} credential from Vault. "
                "Ask a workspace administrator to check the credential configuration."
            ) from None

    if not isinstance(api_key, str) or not api_key.strip():
        raise ValueError(
            f"Lens has no {provider} API key. Add {provider}.api_key in Settings > Vault "
            "in the Vault selected in Lens settings (Default when none is selected)."
        )

    log.debug("glens.llm_resolved", provider=provider, model=model, reason=reason)
    return client_for(provider, api_key=api_key), provider, model


# ── Core tool loop ────────────────────────────────────────────────────────────

_APOLOGY_PHRASES = (
    "there is an issue", "unable to retrieve", "i cannot provide",
    "i am unable", "it seems", "i'm unable", "cannot access",
    "having trouble", "experiencing an issue",
)

def _answer_is_apology(text: str) -> bool:
    low = text.lower()
    return any(p in low for p in _APOLOGY_PHRASES)


def _has_data(final_msgs: list[dict]) -> bool:
    """Return False only when every tool result was an empty/zero-count response."""
    tool_contents = [m.get("content", "") for m in final_msgs if m.get("role") == "tool"]
    if not tool_contents:
        return False
    for content in tool_contents:
        try:
            r = json.loads(content) if isinstance(content, str) else content
            if isinstance(r, dict):
                if "count" in r and int(r["count"]) > 0:
                    return True
                if "count" not in r:
                    return True  # spend/policy/etc results always have data
            elif isinstance(r, list) and len(r) > 0:
                return True
        except Exception:
            return True
    return False


def _iter_tool_results(final_msgs: list[dict]):
    """Yield each tool-result payload (raw). Handles both provider shapes:
    OpenAI/Perplexity: ``{"role": "tool", "content": "<json>"}``
    Anthropic:         ``{"role": "user", "content": [{"type": "tool_result", "content": "<json>"}, ...]}``
    """
    for m in final_msgs:
        content = m.get("content", "")
        if m.get("role") == "tool":
            yield content
        elif m.get("role") == "user" and isinstance(content, list):
            for blk in content:
                if isinstance(blk, dict) and blk.get("type") == "tool_result":
                    yield blk.get("content", "")


def _parse_json_dict(raw) -> dict | None:
    try:
        r = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None
    return r if isinstance(r, dict) else None


def _extract_confirm_envelope(final_msgs: list[dict]) -> dict | None:
    """First tool result whose JSON body has ``confirm_required=True``.
    Surfaces the actor envelope (from ``require_confirmation``) to the SSE
    'done' event so the frontend renders ActionConfirmBubble instead of prose.
    """
    for raw in _iter_tool_results(final_msgs):
        r = _parse_json_dict(raw)
        if r and r.get("confirm_required") and r.get("approval_request_id"):
            return r
    return None


def _extract_run_started_envelope(final_msgs: list[dict]) -> dict | None:
    """First tool result reporting a successful run kickoff (``executed=True``
    + ``result.run_id`` set). Surfaces run metadata to the SSE 'done' event so
    the frontend renders ``<RunBubble>`` inline — same live surface the
    button-click path gets via ActionConfirmBubble (#1480 PR 11).
    """
    for raw in _iter_tool_results(final_msgs):
        r = _parse_json_dict(raw)
        if not r or not r.get("executed"):
            continue
        result = r.get("result")
        if not isinstance(result, dict) or not result.get("run_id"):
            continue
        return {
            "run_id": result["run_id"],
            "workflow_name": result.get("workflow_name") or r.get("tool_name") or "workflow",
            "status": result.get("status") or "pending",
        }
    return None


def _extract_audit_export(final_msgs: list[dict]) -> dict | None:
    """First ``export_audit_log`` result (``kind == "audit_export"``). Surfaces it on the
    SSE 'done' event as ``audit_export`` (and persists it) so the UI renders a Download button."""
    for raw in _iter_tool_results(final_msgs):
        r = _parse_json_dict(raw)
        if r and r.get("kind") == "audit_export" and r.get("download_path"):
            return r
    return None


def _build_drilldown(tool_calls: list[tuple[str, dict]]) -> str | None:
    """Build a grounded drilldown URL from the tool calls the LLM actually made."""
    page = "/logs/guard"
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
        elif name == "get_blocked_workflows":
            page = "/theguard/activity"
            filters["decision"] = "blocked"
            if args.get("since"):    filters["since"] = args["since"]
            if args.get("until"):    filters["until"] = args["until"]
            if args.get("workflow_id"): filters["workflow_id"] = args["workflow_id"]
            if args.get("rule_id"):  filters["rule_id"] = args["rule_id"]
        elif name == "list_workflows":
            page = "/workflows"
        elif name == "get_workflow_details":
            wid = args.get("workflow_id")
            page = f"/workflows/{wid}" if wid else "/workflows"
        elif name in ("list_runs",):
            page = "/runs"
            if args.get("workflow_id"): filters["workflow_id"] = args["workflow_id"]
            if args.get("status"):      filters["status"] = args["status"]
            if args.get("since"):       filters["since"] = args["since"]
            if args.get("until"):       filters["until"] = args["until"]
        elif name == "get_run":
            rid = args.get("run_id")
            page = f"/runs/{rid}" if rid else "/runs"
        elif name in ("list_agent_identities", "get_agent_identity_count"):
            page = "/agent-identity"
            if args.get("status") and args["status"] != "all":
                filters["status"] = args["status"]
        elif name in ("get_spend_summary", "get_savings_summary", "get_budgets"):
            page = "/theguard/spend"
        elif name in ("list_policies", "get_guard_config"):
            page = "/theguard/policies"
        elif name in ("get_discovery_summary",):
            page = "/theguard/discovery"
        elif name in ("get_compliance_status", "get_framework_coverage"):
            page = "/theguard/compliance"
        elif name in ("list_pending_approvals", "get_approval"):
            page = "/theguard/approvals"
            if args.get("status") and args["status"] != "all":
                filters["status"] = args["status"]
        elif name in ("list_installed_packs", "browse_marketplace", "get_pack_details"):
            slug = args.get("slug")
            page = f"/packs/{slug}" if slug else "/packs"
        elif name in ("list_integrations", "get_integration_status"):
            page = "/integrations"
        elif name in ("list_members", "get_member"):
            page = "/theguard/team"
            if args.get("role"):
                filters["role"] = args["role"]
        elif name in ("get_audit_events", "search_audit_log"):
            page = "/audit"
            if args.get("actor_email"):   filters["actor"] = args["actor_email"]
            if args.get("action"):        filters["action"] = args["action"]
            if args.get("resource_type"): filters["resource_type"] = args["resource_type"]
            if args.get("since"):         filters["since"] = args["since"]
            if args.get("until"):         filters["until"] = args["until"]
        elif name == "list_projects":
            page = "/projects"
        elif name == "get_project":
            page = f"/projects/{args.get('id_or_slug')}" if args.get("id_or_slug") else "/projects"
        elif name in ("list_alerts", "get_alert"):
            page = "/observability/alerts"
            if args.get("severity"):   filters["severity"] = args["severity"]
            if args.get("event_type"): filters["event_type"] = args["event_type"]
        elif name == "list_run_events":
            rid = args.get("run_id")
            page = f"/runs/{rid}" if rid else "/runs"

    if not filters and page == "/logs/guard":
        return None
    if "since" in filters and "until" not in filters:
        filters["until"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if filters:
        qs = "&".join(f"{k}={v}" for k, v in filters.items())
        return f"{page}?{qs}"
    return page


def _guarded_openai_completion(executor: Executor, provider: str, model: str,
                                client, messages: list[dict], system: str,
                                tools: list[dict] | None, max_tokens: int):
    """In-process guarded LLM call for Lens — routes through the LLMClient.

    Same composable policy engine as the HTTP proxy, no self-HTTP hop.
    Provider + model come from _llm_config() (workspace primitives)."""
    from app.guard.gateway import guarded_client_call, GuardedLLMBlocked as _Blocked

    try:
        return guarded_client_call(
            client=client,
            workspace_id=executor.workspace_id,
            provider=provider, model=model,
            messages=messages, system=system,
            tools=tools, max_tokens=max_tokens,
            ai_tool="lens",
            clerk_user_id="system:lens",
            agent_identity_id=executor.agent_identity_id,
            prompt_summary="lens.resolve_tools",
            hook_session_id=executor.session_id,
        )
    except _Blocked as blk:
        raise Exception(f"Guard blocked Lens call: {blk.detail}") from blk


def _resolve_tools(messages: list[dict], system: str, executor: Executor) -> tuple[list[dict], str | None, list[tuple[str, dict]]]:
    """Phase 1: Execute tool calls. Returns (final_msgs, early_text, tool_calls_made).

    Each LLM turn goes through Guard's in-process `guarded_llm_call` (#1254) —
    same policy + audit path as the HTTP proxy. Tool dispatch itself goes
    through `lens_adapter.dispatch` (#1227) so Lens shares the same
    ToolRegistry as the MCP HTTP/stdio surfaces. When the LLM emits N
    tool_use blocks in a single turn (Lens commonly does 2-4), they run
    concurrently via `dispatch_tool_blocks` — SQLAlchemy handles concurrent
    sessions on separate connections so this scales cleanly to any tool
    count the DB pool can sustain.
    """
    from app.mcp.lens_adapter import dispatch as lens_dispatch
    from app.mcp.server import MCPContext
    from app.runtime.llm_client import LLMToolUseBlock
    from app.runtime.tool_dispatch import dispatch_tool_blocks

    msgs = list(messages)
    tool_calls_made: list[tuple[str, dict]] = []

    # Same-turn self-confirmation guard (#1465 follow-up): if the LLM emits
    # a proposal + a confirm_pending_action for that proposal's id in the
    # same tool loop, the confirm tool refuses. Populated below after each
    # dispatch by scanning results for `confirm_required` envelopes.
    lens_ctx = MCPContext(
        workspace_id=executor.workspace_id,
        clerk_user_id=executor.clerk_user_id if isinstance(executor.clerk_user_id, str) else "system:lens",
        surface="lens",
        pending_action_ids_this_turn=set(),
    )

    def _bound_dispatcher(name: str, args_json: str) -> str:
        return lens_dispatch(name, args_json, lens_ctx)

    if isinstance(executor.entry_query, dict):
        from app.modules.glens.evidence_explanation import answer_from_result
        name = "get_platform_evidence"
        raw = _bound_dispatcher(name, json.dumps(executor.entry_query))
        answer, query = answer_from_result(raw, executor.workspace_id, name)
        executor.evidence_query, executor.evidence_tool = query or {}, name
        return msgs, answer, [(name, executor.entry_query)]

    client, provider, model = _llm_config(executor)
    log.info("glens.llm_call", provider=provider, model=model)
    for _ in range(5):
        resp = _guarded_openai_completion(
            executor, provider, model, client,
            messages=msgs, system=system, tools=TOOLS, max_tokens=512,
        )
        tool_blocks = [b for b in resp.content if isinstance(b, LLMToolUseBlock)]
        text = next((b.text for b in resp.content if hasattr(b, "text") and b.text), "")

        if not tool_blocks:
            return msgs, text or "I couldn't find relevant data to answer that.", tool_calls_made

        trial = next((b for b in tool_blocks if b.name in {"get_trial_evidence", "get_platform_evidence"}), None)
        if trial is not None:
            from app.modules.glens.evidence_explanation import answer_from_result
            # Evidence is terminal and read-only: do not co-dispatch mutations
            # or feed untrusted record fields into another model turn.
            raw = _bound_dispatcher(trial.name, json.dumps(trial.input))
            answer, query = answer_from_result(raw, executor.workspace_id, trial.name)
            executor.evidence_query = query or {}
            executor.evidence_tool = trial.name
            return msgs, answer, [(trial.name, trial.input)]

        msgs.extend(client.make_assistant_turn(resp))
        for b in tool_blocks:
            tool_calls_made.append((b.name, b.input))
        results = dispatch_tool_blocks(tool_blocks, _bound_dispatcher)
        for name_and_input, (_id, result) in zip(
            [(b.name, b.input) for b in tool_blocks],
            results,
        ):
            log.debug("glens.tool", name=name_and_input[0], result_len=len(result))
        # Register any pending-action ids returned by proposal tools so a
        # follow-up confirm_pending_action/cancel_pending_action in the
        # NEXT iteration of this same tool loop is refused.
        for _id, result_str in results:
            envelope = _parse_json_dict(result_str)
            if envelope and envelope.get("confirm_required"):
                aid = envelope.get("approval_request_id")
                if isinstance(aid, str):
                    lens_ctx.pending_action_ids_this_turn.add(aid)
        msgs.extend(client.make_tool_results_turn(results))

    return msgs, None, tool_calls_made


def _stream_synthesis(msgs: list[dict], system: str, executor: Executor, on_token,
                       lens_session_token: str | None = None) -> str:
    """Phase 2: stream the final synthesis. Guard-enforced end to end.

    Routes through `guarded_client_stream` → `LLMClient.stream()`. Same
    policy engine + audit as Phase 1. Vendor-neutral (env-var selection +
    per-workspace credential vault, same as every other LLMClient
    consumer)."""
    from app.guard.gateway import guarded_client_stream

    client, provider, model = _llm_config(executor)
    log.info("glens.stream_synthesis", provider=provider, model=model)
    text = guarded_client_stream(
        client=client,
        workspace_id=executor.workspace_id,
        provider=provider, model=model,
        messages=msgs, system=system, max_tokens=1024,
        on_token=on_token,
        ai_tool="lens",
        clerk_user_id="system:lens",
        agent_identity_id=executor.agent_identity_id,
        prompt_summary="lens.synthesis",
        hook_session_id=executor.session_id,
    )
    return text or "Could not complete the analysis."


# ── Session helpers used only by the stream endpoint ─────────────────────────

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
                saved = json.loads(m["content"])
                if "evidence_query" in saved:
                    content = "Evidence was requested. Call " + saved.get("evidence_tool", "get_trial_evidence") + " again with current authorization before answering follow-up questions. Previous query: " + json.dumps(saved["evidence_query"])
                else:
                    content = saved.get("answer", m["content"])
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
    entry_context: LensEntryContext | None = None


@router.post("/chat/stream")
async def glens_chat_stream(
    req: ChatRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_permission("guard.activity.view_own")),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    ws_uuid = _parse_workspace_id(workspace_id)
    logger = log.bind(workspace_id=workspace_id)
    entry_query = resolve_entry_context(db, workspace_id, user_id, req.entry_context) if req.entry_context else None

    session = None
    if req.session_id:
        session = _get_session(db, req.session_id, ws_uuid)
    if not session:
        session = GlensChatSession(workspace_id=ws_uuid, title=req.message[:60], messages=json.dumps([]))
        db.add(session)
        db.flush()
        db.commit()

    # Mint session-scoped Lens token — #1218 Step 3b.3.
    # Fresh session with no token OR pre-migration session (token_hash NULL):
    # mint here. Existing session with a live token: overwrite (previous raw
    # token loses access, which is fine — single stream per session).
    # Raw token held in closure state and passed to guarded_completion;
    # never persisted, never returned to the client.
    from app.modules.glens import tokens as _lens_tokens
    _lens_session_token = _lens_tokens.mint_for_session(db, session)

    # Mint a session-scoped AgentIdentity so every Lens LLM egress carries a
    # real `agent_identity_id` through PolicyContext (SpendCap +
    # ThroughputCap activate on the composable engine). Idempotent: only
    # mint if the session doesn't already have one. Plaintext token is
    # discarded — Lens calls are in-process, no HTTP boundary needs it.
    if not getattr(session, "agent_identity_id", None):
        from app.modules.agent_identity.router import mint_agent_identity as _mint_ai
        _identity, _plain = _mint_ai(
            db, workspace_id, f"lens-session-{str(session.id)[:8]}"
        )
        session.agent_identity_id = _identity.id
        db.add(session)
        db.commit()

    session_messages = json.loads(session.messages)
    session_messages.append({"role": "user", "content": req.message})
    session_id_str = str(session.id)
    executor = Executor(
        db, workspace_id,
        agent_identity_id=session.agent_identity_id,
        session_id=session_id_str,
        clerk_user_id=user_id,
    )
    executor.entry_query = entry_query.model_dump(mode="json") if entry_query else None

    _now = datetime.now(timezone.utc)
    today = _now.strftime("%Y-%m-%d")
    # Pre-format the human-readable date so the LLM doesn't reformat and drift
    # (gpt-4o-mini fabricated "August 26" when today was "2026-08-27").
    today_display = _now.strftime("%A, %B %-d, %Y") + " UTC"
    system = _SYSTEM.format(today=today, today_display=today_display)
    if req.page_context:
        system += f"\n\nUser is currently viewing `{req.page_context}`. Prefer answers scoped to that page when ambiguous."
    llm_messages = _build_llm_messages(session_messages)

    loop = asyncio.get_running_loop()
    event_q: asyncio.Queue[dict] = asyncio.Queue()

    async def _run_work() -> None:
        from app.modules.glens.grounding import check_grounded
        try:
            # Phase 1: resolve tool calls (fast, non-streaming)
            final_msgs, early_text, tool_calls = await asyncio.to_thread(_resolve_tools, llm_messages, system, executor)
            drilldown = _build_drilldown(tool_calls) if _has_data(final_msgs) else None
            confirm_envelope = _extract_confirm_envelope(final_msgs)
            run_started_envelope = _extract_run_started_envelope(final_msgs)
            audit_export = _extract_audit_export(final_msgs)

            # #1480 PR 14 — skip prose streaming entirely when we have a
            # run_started envelope. <RunBubble> IS the answer; streaming
            # "Run triggered successfully!" underneath would flash for
            # ~500ms before the frontend replaces it with the bubble.
            if run_started_envelope:
                await event_q.put({"type": "done", "answer": "", "confirm_envelope": confirm_envelope, "run_started_envelope": run_started_envelope, "audit_export": audit_export})
                return

            if early_text:
                answer = early_text
                tool_results = [msg.get("content", "") for msg in final_msgs if msg.get("role") == "tool"]
                check_grounded(answer, tool_results, skill="governance")
                if drilldown:
                    answer += f"\n\n[View all →]({drilldown})"
                # Verified evidence can be longer than model prose. Avoid
                # spending the request timeout on artificial typing delays.
                chunk_size = 128 if executor.evidence_tool else 4
                for i in range(0, len(answer), chunk_size):
                    await event_q.put({"type": "token", "text": answer[i:i + chunk_size]})
                    await asyncio.sleep(0.008)
                await event_q.put({"type": "done", "answer": answer, "confirm_envelope": confirm_envelope, "run_started_envelope": run_started_envelope, "audit_export": audit_export})
                return

            # Phase 2: stream synthesis (tools already resolved)
            def on_token(t: str):
                loop.call_soon_threadsafe(event_q.put_nowait, {"type": "token", "text": t})

            answer = await asyncio.to_thread(_stream_synthesis, final_msgs, system, executor, on_token)
            tool_results = [msg.get("content", "") for msg in final_msgs if msg.get("role") == "tool"]
            check_grounded(answer, tool_results, skill="governance")
            if drilldown and not _answer_is_apology(answer):
                link = f"\n\n[View all →]({drilldown})"
                for i in range(0, len(link), 4):
                    await event_q.put({"type": "token", "text": link[i:i + 4]})
                    await asyncio.sleep(0.008)
                answer += link
            await event_q.put({"type": "done", "answer": answer, "confirm_envelope": confirm_envelope, "run_started_envelope": run_started_envelope, "audit_export": audit_export})
        except Exception as e:
            # If it's a Guard block, surface the rule_id to logs + telemetry.
            # #1286 wired Lens through the same policy engine as the HTTP
            # proxy, so any rule that fires now affects Lens.
            _err_type = type(e).__name__
            _err_detail = str(e)
            logger.error(
                "glens.stream.failed",
                error=_err_detail,
                error_type=_err_type,
                exc_info=True,
            )
            _short = _err_detail if len(_err_detail) <= 200 else _err_detail[:200] + "…"
            await event_q.put({"type": "error", "message": f"{_err_type}: {_short}"})

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
                    answer = mask_secrets(evt["answer"])
                    # Persist envelopes alongside the answer so session
                    # restore (#1480 PR 12) can rehydrate the right bubble
                    # kind — otherwise refresh loses ActionConfirmBubble /
                    # RunBubble and shows the LLM's prose only.
                    persisted: dict[str, Any] = {"answer": answer, "skill": "governance"}
                    if executor.evidence_query is not None:
                        from app.modules.glens.evidence_explanation import SAVED
                        persisted = {"answer": SAVED, "skill": "governance", "evidence_query": executor.evidence_query, "evidence_tool": executor.evidence_tool}
                    if evt.get("confirm_envelope"):
                        persisted["confirm_envelope"] = evt["confirm_envelope"]
                    if evt.get("run_started_envelope"):
                        persisted["run_started"] = evt["run_started_envelope"]
                    if evt.get("audit_export"):
                        persisted["audit_export"] = evt["audit_export"]
                    session_messages.append({
                        "role": "assistant",
                        "content": json.dumps(persisted),
                    })
                    capped = session_messages[-50:]
                    background_tasks.add_task(_bg_save_session, session_id_str, capped, None)

                    done_payload = {"type": "done", "session_id": session_id_str, "skill": "governance", "answer": answer}
                    if evt.get("confirm_envelope"):
                        done_payload.update(evt["confirm_envelope"])
                    if evt.get("run_started_envelope"):
                        done_payload["run_started"] = evt["run_started_envelope"]
                    if evt.get("audit_export"):
                        done_payload["audit_export"] = evt["audit_export"]
                    yield f"data: {json.dumps(done_payload)}\n\n"
                    break
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'error', 'message': 'Request timed out. Please try again.'})}\n\n"
        finally:
            task.cancel()

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            # Force upstream proxies (nginx, Render, Cloudflare) to flush each
            # SSE frame instead of buffering. Without these, tokens arrive in
            # one dump at end-of-stream instead of streaming like GPT/Claude.
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
