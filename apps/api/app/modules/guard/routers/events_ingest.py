"""ConductGuard events — hook ingestion endpoints (POST /guard/events, /session-usage, /usage)."""

import base64
import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from app.modules.guard.session_coverage import apply_session_cost
from sqlalchemy.orm import Session
from app.core.auth import (
    _resolve_agent_token,
)
from app.core.config import settings
from app.core.database import SessionLocal, get_db
from app.core.workspace_context import set_workspace_rls
from app.modules.guard.models import GuardAuditEvent, GuardConfig, GuardSession, chain_hash_for_insert, get_policy_hash
from app.modules.guard.routers.events_common import (
    EventOut,
    HookEvent,
    SessionUsageReport,
    UsageOut,
    UsageUpdate,
    _client_ip_from,
    _event_to_dict,
    _now,
)
from app.modules.guard.routers.events_notify import (
    _check_spend_budget,
    notify_guard_block,
)

log = structlog.get_logger("app.modules.guard.routers.events")

router = APIRouter(prefix="/guard/events", tags=["guard"])


def _hook_authenticated_workspace(
    request: Request,
    db: Session = Depends(get_db),
) -> tuple[str, str | None] | None:
    """Resolve an Agent Identity token during the CLI migration window."""
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer" and token:
        if not token.startswith(("cond_agt_", "cond_api_")):
            raise HTTPException(status_code=401, detail="Agent Identity token required")
        identity, clerk_user_id = _resolve_agent_token(token, db)
        # Preserve the verified identity; never derive attribution from hook input.
        request.state.guard_hook_identity = (str(identity.workspace_id), str(identity.id))
        return str(identity.workspace_id), clerk_user_id
    if settings.guard_require_hook_auth is True:
        raise HTTPException(status_code=401, detail="Authorization header required")
    log.warning("guard.events.legacy_unauthenticated_ingest")
    return None


def _authenticated_workspace_uuid(
    body_workspace_id: str,
    auth_context: tuple[str, str | None] | None,
):
    """Validate the payload workspace against the authenticated token workspace."""
    import uuid

    try:
        body_ws = uuid.UUID(body_workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")
    if auth_context is not None:
        authenticated_workspace_id, _ = auth_context
        try:
            auth_ws = uuid.UUID(authenticated_workspace_id)
        except ValueError:
            raise HTTPException(status_code=403, detail="Authenticated workspace is invalid")
        if body_ws != auth_ws:
            raise HTTPException(
                status_code=403,
                detail="Authenticated token does not belong to the event workspace",
            )
    return body_ws


def _authenticated_actor(
    body: HookEvent,
    auth_context: tuple[str, str | None] | None,
    db: Session,
) -> tuple[str | None, str | None]:
    if auth_context is None:
        return body.clerk_user_id, body.user_email
    _, authenticated_clerk_user_id = auth_context
    if (
        authenticated_clerk_user_id
        and body.clerk_user_id
        and authenticated_clerk_user_id != body.clerk_user_id
    ):
        raise HTTPException(status_code=403, detail="Event actor does not match authenticated token")
    if not authenticated_clerk_user_id:
        return None, None
    try:
        from app.models.user import User

        email = db.query(User.email).filter(User.clerk_id == authenticated_clerk_user_id).scalar()
    except Exception:
        email = None
    return authenticated_clerk_user_id, email if isinstance(email, str) else None


def _decoded_input_summary(body: HookEvent) -> str | None:
    if body.input_summary is None or body.input_summary_encoding is None:
        return body.input_summary
    if body.input_summary_encoding != "base64url":
        raise HTTPException(status_code=422, detail="Unsupported input_summary_encoding")
    try:
        raw = base64.b64decode(body.input_summary, altchars=b"-_", validate=True)
        return raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        raise HTTPException(status_code=422, detail="Invalid base64url input_summary")


def _bg_slack_notify(
    workspace_id_str: str,
    decision: str,
    notify_on_block: bool,
    alert_channel: str | None,
    user_email: str | None,
    clerk_user_id: str | None,
    ai_tool: str | None,
    rule_id: str | None,
    rule_message: str | None,
) -> None:
    """Background task: fan out block/warn notifications for hook events.

    Delegates to notify_guard_block so hook (CLI) events get the same
    per-action-channel fan-out (Slack / webhook / PagerDuty / email) as the
    proxy, MCP, and runtime surfaces. Falls back to the legacy single Slack
    channel automatically when no per-action channels are configured.
    """
    if decision not in ("blocked", "warned"):
        return
    db = SessionLocal()
    try:
        import uuid as _uuid
        ws_uuid = _uuid.UUID(workspace_id_str)
        # Honour the legacy notify_on_block toggle. When it's off AND no
        # per-action channels exist, nothing fires (matches previous behaviour).
        # notify_guard_block itself already handles the "no channels + no legacy
        # config" case, so we just gate the direct legacy-only path here.
        if not notify_on_block:
            # Check per-action channels — if any exist, still fan out. Otherwise
            # respect the operator's opt-out.
            from app.modules.guard.routers.notifications import resolve_channels as _resolve_channels
            _action = "block" if decision == "blocked" else "warn"
            if not _resolve_channels(db, ws_uuid, _action):
                return
        # Resolve Clerk user id to a real email before it lands in the
        # Slack card — otherwise the "User:" line renders as the raw
        # `user_xxx` Clerk id. Same pattern as the MCP writer at
        # routers/mcp.py:717 and the durable-audit path at guard/audit.py:585.
        # get_clerk_user_email() is LRU-cached, so no extra Clerk hits after
        # the first per user.
        _display_email = user_email
        if not _display_email and clerk_user_id:
            try:
                from app.core.auth import get_clerk_user_email as _get_email
                _display_email = _get_email(clerk_user_id)
            except Exception:
                pass
        notify_guard_block(
            db, ws_uuid,
            decision=decision,
            rule_id=rule_id,
            user_email=_display_email or clerk_user_id,
            tool=ai_tool,
            source="hook",
        )
    except Exception as exc:
        log.warning("guard.slack_notification_failed", exc=str(exc))
    finally:
        db.close()


def _bg_spend_and_scan(
    workspace_id_str: str,
    decision: str,
    automation_security_scan: bool,
    ai_tool: str | None,
    rule_id: str | None,
    rule_message: str | None,
    user_email: str | None,
    blast_radius: dict | None,
    event_id: str,
) -> None:
    """Background task: spend budget check + optional security loop scan."""
    db = SessionLocal()
    try:
        import uuid as _uuid
        ws_uuid = _uuid.UUID(workspace_id_str)
        config = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
        # Spend budget check
        try:
            _check_spend_budget(db, workspace_id_str, config=config)
        except Exception as exc:
            log.warning("guard.spend_budget_check_failed", exc=str(exc))
    finally:
        db.close()


def _bg_project_event(event_id: str, workspace_id: str) -> None:
    """Background task: project a GuardAuditEvent into the knowledge index."""
    db = SessionLocal()
    try:
        from app.modules.guard.knowledge import project_audit_event
        event = db.query(GuardAuditEvent).filter(GuardAuditEvent.id == event_id).first()
        if event:
            project_audit_event(event, db)
    except Exception as exc:
        log.warning("guard.knowledge.bg_project_failed", event_id=event_id, error=str(exc))
    finally:
        db.close()


@router.post("/session-usage", response_model=EventOut, status_code=201)
def ingest_session_usage(
    body: SessionUsageReport,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    auth_context: tuple[str, str | None] | None = Depends(_hook_authenticated_workspace),
):
    """Record reported client session deltas, never per-tool or Gateway spend."""
    from uuid import NAMESPACE_URL, uuid5

    ws_uuid = _authenticated_workspace_uuid(str(body.workspace_id), auth_context)
    if body.observed_at.tzinfo is None:
        raise HTTPException(status_code=422, detail="observed_at must include a timezone")
    # Serialize duplicate delivery, including a retry after a lost response.
    config = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).with_for_update().first()
    if not config:
        raise HTTPException(status_code=404, detail="workspace_id not found in guard_config")
    actor = auth_context[1] if auth_context else None
    namespace = "copilot-usage" if body.ai_tool == "copilot-cli" else f"{body.ai_tool}-usage"
    event_id = uuid5(NAMESPACE_URL, f"conduct:{namespace}:{ws_uuid}:{actor}:{body.hook_session_id}:{body.snapshot_id}")
    existing = db.query(GuardAuditEvent).filter(
        GuardAuditEvent.id == event_id, GuardAuditEvent.workspace_id == ws_uuid,
    ).first()
    if existing:
        return EventOut(**_event_to_dict(existing))
    event = HookEvent(
        workspace_id=str(ws_uuid), ai_tool=body.ai_tool, tool_call="session_usage",
        decision="audited", hook_session_id=str(body.hook_session_id), receipt_id=str(event_id),
        tokens_before=body.input_tokens, tokens_after=body.output_tokens,
        rule_message=(f"{body.ai_tool} reported session usage since the previous usage snapshot. "
                      "Cache and reasoning tokens are included once. "
                      f"Observed at {body.observed_at.isoformat()}. Client reported; not Gateway usage."),
    )
    apply_session_cost(event, body, db, ws_uuid, actor, request)
    return ingest_event(event, request, background, db, auth_context)


@router.post("", response_model=EventOut, status_code=201)
def ingest_event(
    body: HookEvent,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    auth_context: tuple[str, str | None] | None = Depends(_hook_authenticated_workspace),
):
    """Ingest an authenticated hook event bound to its token workspace."""
    import uuid

    ws_uuid = _authenticated_workspace_uuid(body.workspace_id, auth_context)
    # Projection intent/summary tables enforce FORCE RLS. Set the canonical,
    # authenticated workspace on this same transaction before any source or
    # outbox persistence so the raw event and projection remain atomic.
    set_workspace_rls(db, ws_uuid)
    actor_clerk_user_id, actor_email = _authenticated_actor(body, auth_context, db)
    verified_identity = getattr(request.state, "guard_hook_identity", None)
    agent_identity_id = None
    if auth_context is not None and isinstance(verified_identity, tuple):
        identity_workspace, agent_identity_id = verified_identity
        if identity_workspace != str(ws_uuid):
            raise HTTPException(status_code=403, detail="Event identity workspace mismatch")

    config = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    if not config:
        raise HTTPException(status_code=404, detail="workspace_id not found in guard_config")

    now = _now()

    # 1. Compute hash-chain + policy BOM fields before insert
    prev_hash, entry_hash = chain_hash_for_insert(db, ws_uuid, now, body.tool_call, body.decision)
    policy_hash = get_policy_hash(db, ws_uuid)

    # 2. Write the audit event
    _event_id: uuid.UUID | None = None
    if body.receipt_id:
        try:
            _event_id = uuid.UUID(body.receipt_id)
        except ValueError:
            _event_id = None
    event = GuardAuditEvent(
        id=_event_id or uuid.uuid4(),
        workspace_id=ws_uuid,
        clerk_user_id=actor_clerk_user_id,
        agent_identity_id=agent_identity_id,
        session_id=body.session_id,
        user_email=actor_email,
        ai_tool=body.ai_tool,
        tool_call=body.tool_call,
        input_summary=_decoded_input_summary(body),
        decision=body.decision,
        rule_id=body.rule_id,
        rule_message=body.rule_message,
        tokens_before=body.tokens_before,
        tokens_after=body.tokens_after,
        tokens_saved=body.tokens_saved,
        cost_usd_before=body.cost_usd_before,
        cost_usd_after=body.cost_usd_after,
        conductai_run_id=body.conductai_run_id,
        conductai_workflow=body.conductai_workflow,
        duration_ms=body.duration_ms,
        tool_use_id=body.tool_use_id,
        hook_session_id=body.hook_session_id,
        blast_radius=body.blast_radius,
        ts=now,
        previous_hash=prev_hash,
        entry_hash=entry_hash,
        policy_hash=policy_hash,
        goal_id=body.goal_id,
        goal_name=body.goal_name,
        routing_meta={"session_usage": body._session_usage} if body._session_usage else None,
        evaluated_rules=body.evaluated_rules,
        defense_score=body.defense_score,
    )
    db.add(event)
    db.flush()  # get event.id before commit

    # A hook report is evidence for this installation, not universal protection.
    try:
        from app.modules.guard.discovery_inventory import observe_hook
        with db.begin_nested():
            observe_hook(db, ws_uuid, body.discovery_device_id, body.discovery_installation_id,
                         {"claude_code": "claude-code", "codex_cli": "codex", "codex-desktop": "codex"}.get(body.ai_tool, body.ai_tool),
                         event.id, now)
    except Exception:
        pass  # never block a hook event over a telemetry write

    # 2. Auto-resolve or create a GuardSession from hook_session_id
    resolved_session_id = body.session_id
    if body.hook_session_id and not resolved_session_id:
        prior = (
            db.query(GuardAuditEvent.session_id)
            .filter(
                GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.hook_session_id == body.hook_session_id,
                GuardAuditEvent.session_id.isnot(None),
                GuardAuditEvent.id != event.id,
            )
            .first()
        )
        if prior and prior.session_id:
            resolved_session_id = str(prior.session_id)
        else:
            new_sess = GuardSession(
                workspace_id=ws_uuid,
                user_email=actor_email,
                clerk_user_id=actor_clerk_user_id,
                ai_tool=body.ai_tool,
                started_at=now,
            )
            db.add(new_sess)
            db.flush()
            resolved_session_id = str(new_sess.id)
        event.session_id = uuid.UUID(resolved_session_id)
        db.flush()

    if resolved_session_id:
        session = (
            db.query(GuardSession)
            .filter(GuardSession.id == resolved_session_id)
            .first()
        )
        if session:
            session.total_tokens_before += body.tokens_before or 0
            session.total_tokens_after += body.tokens_after or 0
            session.total_cost_usd += body.cost_usd_after or 0.0
            session.total_saved_usd += (
                (body.cost_usd_before or 0.0) - (body.cost_usd_after or 0.0)
            )
            session.event_count += 1
            if body.decision in ("blocked", "warned"):
                session.violations_count += 1
            # Capture IP and OS on first event for this session.
            # Uses trusted-proxy-aware parsing (audit S12) — blindly reading
            # the first X-Forwarded-For hop let a caller forge the recorded
            # IP on their own session rows. See _client_ip_from above.
            if not session.client_ip:
                session.client_ip = _client_ip_from(request)
            if not session.os_info and body.os_info:
                session.os_info = body.os_info[:128]
            if not session.hostname and body.hostname:
                session.hostname = body.hostname[:255]

    db.flush()
    db.refresh(event)

    projection_message = None
    if settings.guard_projection_queue_enabled and not settings.guard_projection_paused:
        from app.modules.guard.projection_queue import persist_audit_event_projection
        projection_message = persist_audit_event_projection(
            db,
            event,
            evaluated_rules=body.evaluated_rules,
            now=now,
        )

    # Source + durable intent/summary commit atomically. Redis is best-effort after commit.
    db.commit()
    if projection_message is not None:
        from app.modules.guard.projection_queue import dispatch_projection_message, mark_projection_dispatched
        if dispatch_projection_message(projection_message):
            mark_projection_dispatched(projection_message)

    # Slack notification (background — non-fatal, must not delay response)
    background.add_task(
        _bg_slack_notify,
        workspace_id_str=body.workspace_id,
        decision=body.decision,
        notify_on_block=bool(config.notify_on_block),
        alert_channel=config.alert_channel,
        user_email=actor_email,
        clerk_user_id=actor_clerk_user_id,
        ai_tool=body.ai_tool,
        rule_id=body.rule_id,
        rule_message=body.rule_message,
    )

    # Spend budget check + security loop scan (background — non-fatal)
    background.add_task(
        _bg_spend_and_scan,
        workspace_id_str=body.workspace_id,
        decision=body.decision,
        automation_security_scan=bool(config.automation_security_scan),
        ai_tool=body.ai_tool,
        rule_id=body.rule_id,
        rule_message=body.rule_message,
        user_email=actor_email,
        blast_radius=body.blast_radius,
        event_id=str(event.id),
    )

    # Rollout compatibility: legacy direct projection remains until the queue is enabled.
    if not settings.guard_projection_paused and not settings.guard_projection_queue_enabled:
        background.add_task(_bg_project_event, str(event.id), body.workspace_id)

    return EventOut(**_event_to_dict(event))


# Adding a new AI tool: (1) append its key to config/ai_tools.json so it
# appears in the Spend UI's per-tool cap dropdown, (2) add a matching entry
# below with input/output pricing (USD per 1M tokens). Prefix fallback
# (_tool_pricing) is a safety net, not the source of truth.
TOOL_PRICING = {
    # Claude surfaces (all billed at Sonnet-class rates)
    "claude-code":    {"input": 3.0,  "output": 15.0},
    "claude_code":    {"input": 3.0,  "output": 15.0},
    "claude-chat":    {"input": 3.0,  "output": 15.0},
    "claude_chat":    {"input": 3.0,  "output": 15.0},
    "claude-desktop": {"input": 3.0,  "output": 15.0},
    "claude_desktop": {"input": 3.0,  "output": 15.0},
    "claude-work":    {"input": 3.0,  "output": 15.0},
    "claude_work":    {"input": 3.0,  "output": 15.0},
    # Codex surfaces
    "codex":          {"input": 2.5,  "output": 10.0},
    "codex-cli":      {"input": 2.5,  "output": 10.0},
    "codex_cli":      {"input": 2.5,  "output": 10.0},
    "codex-chat":     {"input": 2.5,  "output": 10.0},
    "codex_chat":     {"input": 2.5,  "output": 10.0},
    "codex-desktop":  {"input": 2.5,  "output": 10.0},
    "codex_desktop":  {"input": 2.5,  "output": 10.0},
    # Other tools
    "cursor":         {"input": 3.0,  "output": 15.0},
    "windsurf":       {"input": 3.0,  "output": 15.0},
    "copilot":        {"input": 3.0,  "output": 15.0},
    "gemini":         {"input": 1.25, "output": 5.0},
    "unknown":        {"input": 3.0,  "output": 15.0},
}


def _tool_pricing(tool_key: str) -> dict:
    """Lookup pricing by exact key, then prefix (claude* / codex*), else unknown."""
    if tool_key in TOOL_PRICING:
        return TOOL_PRICING[tool_key]
    if tool_key.startswith("claude"):
        return TOOL_PRICING["claude-code"]
    if tool_key.startswith("codex"):
        return TOOL_PRICING["codex"]
    return TOOL_PRICING["unknown"]


@router.post("/usage", response_model=UsageOut, status_code=200)
def update_usage(
    body: UsageUpdate,
    db: Session = Depends(get_db),
    auth_context: tuple[str, str | None] | None = Depends(_hook_authenticated_workspace),
):
    """Backfill token counts for an event in the authenticated workspace."""
    ws_uuid = _authenticated_workspace_uuid(body.workspace_id, auth_context)

    config = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    if not config:
        raise HTTPException(status_code=404, detail="workspace_id not found in guard_config")

    try:
        q = (
            db.query(GuardAuditEvent)
            .filter(
                GuardAuditEvent.workspace_id == ws_uuid,
                GuardAuditEvent.hook_session_id == body.hook_session_id,
                GuardAuditEvent.tokens_before.is_(None),
            )
        )
        if body.tool_name:
            q = q.filter(GuardAuditEvent.tool_call == body.tool_name)
        if body.tool_use_id:
            q = q.filter(GuardAuditEvent.tool_use_id == body.tool_use_id)
        if auth_context and auth_context[1]:
            q = q.filter(GuardAuditEvent.clerk_user_id == auth_context[1])
        event = q.order_by(GuardAuditEvent.ts.desc()).first()
    except Exception:
        return UsageOut(updated=False)

    if not event:
        return UsageOut(updated=False)

    tool_key = (body.ai_tool or "unknown").lower()
    pricing = _tool_pricing(tool_key)
    input_price  = pricing["input"]
    output_price = pricing["output"]

    cost_before = (
        body.tokens_input / 1_000_000 * input_price
        + body.tokens_output / 1_000_000 * output_price
    ) if body.tokens_input is not None and body.tokens_output is not None else None
    cost_after = (0.0 if event.decision == "blocked" else cost_before) if cost_before is not None else None
    tokens_saved = body.tokens_input if event.decision == "blocked" else (0 if cost_before is not None else None)

    event.tokens_before   = body.tokens_input
    event.tokens_after    = body.tokens_output
    event.tokens_saved    = tokens_saved
    event.cost_usd_before = cost_before
    event.cost_usd_after  = cost_after
    if body.duration_ms is not None:
        event.duration_ms = body.duration_ms
    if body.blast_radius is not None:
        event.blast_radius = body.blast_radius
    if body.execution_status is not None:
        event.execution_status = body.execution_status
    if body.result_summary is not None:
        event.result_summary = body.result_summary

    db.commit()

    return UsageOut(updated=True)
