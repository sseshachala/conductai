"""
POST /guard/events          — ingest hook event (called by guardctl binary)
GET  /guard/events          — paginated list, filterable
GET  /guard/events/stream   — SSE real-time feed
"""
import asyncio
import hashlib
import json
from datetime import datetime, timezone

import structlog

log = structlog.get_logger(__name__)

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, _clerk_enabled, _verify_clerk_token
from app.core.database import SessionLocal, get_db
from app.models.workspace import Workspace
from app.modules.guard.models import DiscoveredAgent, GuardAuditEvent, GuardConfig, GuardSession, GuardSpendBudget, chain_hash_for_insert, get_policy_hash

router = APIRouter(prefix="/guard/events", tags=["guard"])

SSE_POLL_INTERVAL = 2    # seconds between DB polls
SSE_MAX_DURATION  = 300  # reconnect after 5 min


def _org_ws_subquery(db, workspace_id: str):
    """Return a subquery of all workspace IDs in the same org.

    Falls back to a single-workspace filter when the workspace has no org_id.
    """
    import uuid as _uuid
    ws_uuid = _uuid.UUID(workspace_id)
    ws = db.query(Workspace).filter(Workspace.id == ws_uuid).first()
    if ws and ws.org_id:
        return db.query(Workspace.id).filter(Workspace.org_id == ws.org_id)
    if ws and ws.owner_id:
        return db.query(Workspace.id).filter(Workspace.owner_id == ws.owner_id)
    return db.query(Workspace.id).filter(Workspace.id == ws_uuid)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class HookEvent(BaseModel):
    workspace_id: str
    clerk_user_id: str | None = None
    session_id: str | None = None
    user_email: str | None = None
    ai_tool: str                      # claude_code | claude_chat | claude_desktop | claude_work | codex | codex_cli | codex_chat | cursor | copilot | windsurf | gemini
    tool_call: str                    # bash | edit | write | read
    input_summary: str | None = None
    decision: str                     # allowed | blocked | warned | approval
    rule_id: str | None = None
    rule_message: str | None = None
    tokens_before: int | None = None
    tokens_after: int | None = None
    tokens_saved: int | None = None
    cost_usd_before: float | None = None
    cost_usd_after: float | None = None
    conductai_run_id: str | None = None
    conductai_workflow: str | None = None
    duration_ms: int | None = None
    tool_use_id: str | None = None
    hook_session_id: str | None = None
    blast_radius: dict | None = None
    os_info: str | None = None
    hostname: str | None = None
    goal_id:   str | None = None
    goal_name: str | None = None
    # #1150 phase 1 — layered verdict envelope; hooks may forward the same shape
    evaluated_rules: list[dict] | None = None
    defense_score: int | None = None


class UsageUpdate(BaseModel):
    workspace_id: str
    hook_session_id: str
    tool_name: str | None = None
    tokens_input: int
    tokens_output: int
    duration_ms: int | None = None
    ai_tool: str | None = None   # for pricing
    blast_radius: dict | None = None
    execution_status: str | None = None   # success | error | timeout
    result_summary: str | None = None


class UsageOut(BaseModel):
    updated: bool


class EventOut(BaseModel):
    id: str
    workspace_id: str
    clerk_user_id: str | None
    session_id: str | None
    hook_session_id: str | None = None
    user_email: str | None
    ai_tool: str
    tool_call: str | None
    source: str = "hook"
    provider: str | None = None
    model: str | None = None
    input_summary: str | None
    decision: str
    rule_id: str | None
    rule_message: str | None
    tokens_before: int | None
    tokens_after: int | None
    tokens_saved: int | None
    cost_usd_before: float | None
    cost_usd_after: float | None
    conductai_run_id: str | None
    conductai_workflow: str | None
    conductai_workflow_id: str | None = None
    duration_ms: int | None
    blast_radius: dict | None = None
    ts: str
    entry_hash: str | None = None
    policy_hash: str | None = None
    goal_id:   str | None = None
    goal_name: str | None = None
    # #1150 phase 1 — layered verdict envelope (nullable for pre-migration rows)
    evaluated_rules: list[dict] | None = None
    defense_score: int | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _event_to_dict(e: GuardAuditEvent) -> dict:
    return {
        "id": str(e.id),
        "workspace_id": str(e.workspace_id),
        "clerk_user_id": e.clerk_user_id,
        "session_id": str(e.session_id) if e.session_id else None,
        "hook_session_id": e.hook_session_id,
        "user_email": e.user_email,
        "ai_tool": e.ai_tool,
        "tool_call": e.tool_call,
        "source": e.source or "hook",
        "provider": e.provider,
        "model": e.model,
        "input_summary": e.input_summary,
        "decision": e.decision,
        "rule_id": e.rule_id,
        "rule_message": e.rule_message,
        "tokens_before": e.tokens_before,
        "tokens_after": e.tokens_after,
        "tokens_saved": e.tokens_saved,
        "cost_usd_before": e.cost_usd_before,
        "cost_usd_after": e.cost_usd_after,
        "conductai_run_id": e.conductai_run_id,
        "conductai_workflow": e.conductai_workflow,
        "conductai_workflow_id": e.conductai_workflow_id,
        "duration_ms": e.duration_ms,
        "blast_radius": e.blast_radius,
        "ts": e.ts.isoformat(),
        "entry_hash": e.entry_hash,
        "evaluated_rules": e.evaluated_rules,
        "defense_score": e.defense_score,
        "policy_hash": e.policy_hash,
        "goal_id": e.goal_id,
        "goal_name": e.goal_name,
    }


def notify_guard_block(
    db: Session, workspace_id, *,
    decision: str, rule_id: str | None,
    user_email: str | None, tool: str | None = None,
    provider: str | None = None, source: str = "hook",
) -> None:
    """Single entry point for Guard block/warn Slack notifications.

    Fans out via the #1142 per-action-tier notification channels table when any
    rows exist for this workspace + action; falls back to the legacy single-
    channel setup on guard_config otherwise. Once the operator adds a channel
    via /theguard/settings > Notifications, that new config takes over.
    """
    import uuid as _uuid
    from app.modules.guard.models import GuardConfig as _GC
    from app.modules.guard.routers.notifications import resolve_channels as _resolve_channels
    ws = _uuid.UUID(str(workspace_id)) if not isinstance(workspace_id, _uuid.UUID) else workspace_id
    cfg = db.query(_GC).filter(_GC.workspace_id == ws).first()

    icon = "🚨" if decision == "blocked" else "⚠️"
    lines = [f"{icon} *Guard {decision}* — `{rule_id or source}`"]
    if user_email:
        lines.append(f"• User: {user_email}")
    if tool:
        lines.append(f"• Tool: `{tool}`")
    if provider:
        lines.append(f"• Provider: `{provider}` · via {source}")
    text_msg = "\n".join(lines)

    # #1142 Phase 1+2A+2B+2C — fan out to per-action channels if configured.
    # Split by channel_type: each transport gets a shape it can consume.
    action = "block" if decision == "blocked" else "warn" if decision == "warned" else "audit"
    channels = _resolve_channels(db, ws, action)
    if channels:
        by_type: dict[str, list] = {"slack": [], "webhook": [], "pagerduty": [], "email": []}
        for c in channels:
            by_type.setdefault(c.channel_type, []).append(c)
        if by_type["slack"]:
            _fanout_slack(db, ws, by_type["slack"], text_msg)
        if by_type["webhook"]:
            _fanout_webhook(by_type["webhook"], {
                "event": "guard.decision",
                "action": action,
                "decision": decision,
                "rule_id": rule_id,
                "workspace_id": str(ws),
                "user_email": user_email,
                "tool": tool,
                "provider": provider,
                "source": source,
                "message": text_msg,
            })
        if by_type["pagerduty"]:
            _fanout_pagerduty(by_type["pagerduty"], action, rule_id, text_msg)
        if by_type["email"]:
            _fanout_email(
                db, ws, by_type["email"],
                subject=f"[Guard {decision}] {rule_id or source}",
                html=(
                    f"<p><strong>Guard {decision}</strong> — rule <code>{rule_id or source}</code></p>"
                    + (f"<p>User: {user_email}</p>" if user_email else "")
                    + (f"<p>Tool: <code>{tool}</code></p>" if tool else "")
                    + (f"<p>Provider: <code>{provider}</code> via {source}</p>" if provider else "")
                ),
            )
        return

    # Legacy fallback — single alert_channel gated by notify_on_block.
    if not cfg or not cfg.notify_on_block:
        return
    _send_guard_slack(db, cfg, text_msg)


def _fanout_slack(db: Session, workspace_id, channels, text_msg: str) -> None:
    """Post text_msg to every Slack channel in `channels`. Silently skips any
    that lack credentials or fail — one bad channel must not block the others.

    Per-channel env: honors channel.integration_id via slack_token_for_channel;
    falls back to the workspace-default Slack cred when not set."""
    from app.core.credentials import get_credential
    from app.modules.guard.routers.notifications import slack_token_for_channel
    from app.runtime.integrations.slack import post_message

    try:
        default_creds = get_credential(db, str(workspace_id), "slack")
    except Exception:
        default_creds = None
    default_token = (default_creds or {}).get("token") or (default_creds or {}).get("bot_token") or ""

    for ch in channels:
        if ch.channel_type != "slack":
            continue
        token = slack_token_for_channel(db, workspace_id, ch.integration_id, default_token)
        if not token:
            continue
        try:
            post_message(token=token, channel=ch.channel_ref, text=text_msg)
        except Exception:
            pass  # per-channel failure must not stop the fan-out


def _pd_severity(action: str) -> str:
    return {"block": "error", "approval": "error", "warn": "warning", "audit": "info"}.get(action, "info")


def _fanout_pagerduty(channels, action: str, rule_id, message: str) -> None:
    """POST a PagerDuty Events API v2 trigger for each channel.
    channel_ref is the routing key (integration key from a PD service)."""
    if not channels:
        return
    try:
        import httpx
    except ImportError:
        return
    body_template = {
        "event_action": "trigger",
        "payload": {
            "summary": f"Guard {action}: {rule_id or 'policy event'}",
            "severity": _pd_severity(action),
            "source": "conduct-guard",
            "custom_details": {"message": message},
        },
    }
    for ch in channels:
        if ch.channel_type != "pagerduty":
            continue
        try:
            payload = dict(body_template)
            payload["routing_key"] = ch.channel_ref
            payload["dedup_key"] = f"conduct-guard-{ch.id}-{rule_id or 'noid'}"
            httpx.post("https://events.pagerduty.com/v2/enqueue", json=payload, timeout=10.0)
        except Exception:
            pass


def _fanout_email(db, workspace_id, channels, subject: str, html: str) -> None:
    """Send an email to each recipient. Uses app.core.email.send_email which
    handles workspace-scoped Resend/SendGrid credentials + platform fallback."""
    if not channels:
        return
    try:
        from app.core.email import send_email
    except ImportError:
        return
    for ch in channels:
        if ch.channel_type != "email":
            continue
        try:
            send_email(
                to=ch.channel_ref,
                subject=subject,
                html=html,
                workspace_id=str(workspace_id),
                db=db,
            )
        except Exception:
            pass


def _fanout_webhook(channels, payload: dict) -> None:
    """POST a JSON payload to every webhook channel. Same fail-soft contract
    as _fanout_slack — one bad URL does not block the others."""
    if not channels:
        return
    try:
        import httpx
    except ImportError:
        return
    for ch in channels:
        if ch.channel_type != "webhook":
            continue
        try:
            httpx.post(ch.channel_ref, json=payload, timeout=10.0)
        except Exception:
            pass  # per-channel failure must not stop the fan-out


def _send_guard_slack(db: Session, config: GuardConfig, text_msg: str) -> None:
    """Fire-and-forget Slack notification. Silently skips if not configured."""
    from app.core.credentials import get_credential

    if not config.alert_channel:
        return

    try:
        creds = get_credential(db, str(config.workspace_id), "slack")
        if not creds:
            return
        token = creds.get("token") or creds.get("bot_token", "")
        if not token:
            return
        from app.runtime.integrations.slack import post_message
        post_message(token=token, channel=config.alert_channel, text=text_msg)
    except Exception:
        pass  # never crash ingest on Slack failure


def _check_spend_budget(db: Session, workspace_id: str, config: GuardConfig | None = None) -> None:
    """Log a warning (and send Slack alert) if any active budget has exceeded alert_threshold_pct."""
    import uuid
    from sqlalchemy import func

    now = _now()
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return

    budgets = (
        db.query(GuardSpendBudget)
        .filter(GuardSpendBudget.workspace_id == ws_uuid)
        .all()
    )
    if not budgets:
        return

    monthly_cost = (
        db.query(func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0))
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= period_start,
        )
        .scalar()
    ) or 0.0

    cfg = config or db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()

    for budget in budgets:
        threshold_usd = budget.monthly_limit_usd * (budget.alert_threshold_pct / 100.0)
        if monthly_cost >= threshold_usd and budget.monthly_limit_usd > 0:
            pct_used = (monthly_cost / budget.monthly_limit_usd) * 100
            # Only alert once per 5% increment to avoid spam
            pct_bucket = int(pct_used // 5) * 5
            last_alerted = getattr(budget, "last_alert_pct_bucket", None)
            if last_alerted is not None and pct_bucket <= last_alerted:
                continue
            try:
                budget.last_alert_pct_bucket = pct_bucket
                db.commit()
            except Exception:
                db.rollback()

            scope = f"user={budget.clerk_user_id}" if budget.clerk_user_id else "workspace-wide"
            log.info(
                "guard.spend_alert",
                workspace_id=workspace_id,
                scope=scope,
                monthly_cost_usd=round(monthly_cost, 4),
                threshold_usd=round(threshold_usd, 4),
                alert_threshold_pct=budget.alert_threshold_pct,
                budget_usd=budget.monthly_limit_usd,
            )
            if cfg and cfg.notify_on_budget:
                who = f"user={budget.clerk_user_id}" if budget.clerk_user_id else "workspace-wide"
                msg = (
                    f"\u26a0\ufe0f *Guard spend alert* ({who}): "
                    f"${monthly_cost:.2f} of ${budget.monthly_limit_usd:.2f} used ({round(pct_used)}%) \u2014 "
                    f"alert threshold {budget.alert_threshold_pct}% reached"
                )
                _send_guard_slack(db, cfg, msg)


# ── POST /guard/events — ingest ───────────────────────────────────────────────

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
        notify_guard_block(
            db, ws_uuid,
            decision=decision,
            rule_id=rule_id,
            user_email=user_email or clerk_user_id,
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


@router.post("", response_model=EventOut, status_code=201)
def ingest_event(
    body: HookEvent,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Ingest a hook event from the guardctl binary. No workspace auth —
    workspace_id in the payload is validated against guard_config (same trust
    model as before: possession of the workspace_id is the trust anchor)."""
    import uuid

    try:
        ws_uuid = uuid.UUID(body.workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")

    config = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    if not config:
        raise HTTPException(status_code=404, detail="workspace_id not found in guard_config")

    now = _now()

    # 1. Compute hash-chain + policy BOM fields before insert
    prev_hash, entry_hash = chain_hash_for_insert(db, ws_uuid, now, body.tool_call, body.decision)
    policy_hash = get_policy_hash(db, ws_uuid)

    # 2. Write the audit event
    event = GuardAuditEvent(
        workspace_id=ws_uuid,
        clerk_user_id=body.clerk_user_id,
        session_id=body.session_id,
        user_email=body.user_email,
        ai_tool=body.ai_tool,
        tool_call=body.tool_call,
        input_summary=body.input_summary,
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
    )
    db.add(event)
    db.flush()  # get event.id before commit

    # Self-register: every hook event proves this agent is under Guard.
    try:
        _loc = body.hostname or "local"
        _framework = body.ai_tool or "unknown"
        db.execute(_sql("""
            INSERT INTO discovered_agents
                (id, workspace_id, name, framework, source, location, under_guard, first_seen_at, last_seen_at)
            VALUES
                (gen_random_uuid(), :ws, :name, :fw, 'hook', :loc, true, :now, :now)
            ON CONFLICT (workspace_id, framework, source)
            DO UPDATE SET under_guard = true, last_seen_at = :now
        """), {"ws": ws_uuid, "name": _framework, "fw": _framework, "loc": _loc, "now": now})
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
                user_email=body.user_email,
                clerk_user_id=body.clerk_user_id,
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
            # Capture IP and OS on first event for this session
            if not session.client_ip:
                forwarded = request.headers.get("x-forwarded-for")
                session.client_ip = (forwarded.split(",")[0].strip() if forwarded else None) or (request.client.host if request.client else None)
            if not session.os_info and body.os_info:
                session.os_info = body.os_info[:128]
            if not session.hostname and body.hostname:
                session.hostname = body.hostname[:255]

    db.flush()
    db.refresh(event)

    # 3 & 4 & 5: commit DB writes first, then dispatch non-fatal work to background
    db.commit()

    # Slack notification (background — non-fatal, must not delay response)
    background.add_task(
        _bg_slack_notify,
        workspace_id_str=body.workspace_id,
        decision=body.decision,
        notify_on_block=bool(config.notify_on_block),
        alert_channel=config.alert_channel,
        user_email=body.user_email,
        clerk_user_id=body.clerk_user_id,
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
        user_email=body.user_email,
        blast_radius=body.blast_radius,
        event_id=str(event.id),
    )

    # Knowledge index projection (background — non-fatal, powers GLens search)
    background.add_task(_bg_project_event, str(event.id), body.workspace_id)

    return EventOut(**_event_to_dict(event))


# ── POST /guard/events/usage — PostToolUse token backfill ────────────────────

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
):
    """Backfill real token counts from the PostToolUse hook. No Clerk auth —
    workspace_id validated against guard_config (same trust model as ingest_event)."""
    import uuid

    try:
        ws_uuid = uuid.UUID(body.workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")

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
        body.tokens_input  / 1_000_000 * input_price
        + body.tokens_output / 1_000_000 * output_price
    )
    cost_after = 0.0 if event.decision == "blocked" else cost_before
    tokens_saved = body.tokens_input if event.decision == "blocked" else 0

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


# ── GET /guard/events — paginated list ────────────────────────────────────────

@router.get("", response_model=list[EventOut])
def list_events(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    decision: str | None = Query(default=None, description="allowed|blocked|warned|approval"),
    ai_tool: str | None = Query(default=None, description="claude_code|claude_chat|claude_desktop|claude_work|codex|codex_cli|codex_chat|cursor|copilot|windsurf|gemini"),
    user_email: str | None = Query(default=None),
    rule_id: str | None = Query(default=None, description="Filter to events that fired a specific rule"),
    since: datetime | None = Query(default=None, description="ISO datetime lower bound"),
    until: datetime | None = Query(default=None, description="ISO datetime upper bound"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Paginated, filterable audit event list for a workspace."""
    org_ws = _org_ws_subquery(db, workspace_id)

    q = db.query(GuardAuditEvent).filter(GuardAuditEvent.workspace_id.in_(org_ws))
    if decision:
        q = q.filter(GuardAuditEvent.decision == decision)
    if ai_tool:
        q = q.filter(GuardAuditEvent.ai_tool == ai_tool)
    if user_email:
        q = q.filter(GuardAuditEvent.user_email == user_email)
    if rule_id:
        q = q.filter(GuardAuditEvent.rule_id == rule_id)
    if since:
        q = q.filter(GuardAuditEvent.ts >= since)
    if until:
        q = q.filter(GuardAuditEvent.ts <= until)

    rows = (
        q.order_by(GuardAuditEvent.ts.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [EventOut(**_event_to_dict(e)) for e in rows]


# ── GET /guard/events/cost-trend ─────────────────────────────────────────────

@router.get("/cost-trend")
def cost_trend(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    period: str = Query(default="daily", description="daily|weekly|monthly"),
    tz_offset: int = Query(default=0, description="Client UTC offset in minutes (e.g. -330 for IST, 300 for US/ET)"),
):
    """Return aggregated cost per period, split by ai_tool (claude-code vs codex).
    tz_offset shifts timestamps into the user's local day before bucketing."""
    from datetime import timedelta
    from sqlalchemy import func, text as _text

    org_ws = _org_ws_subquery(db, workspace_id)
    now = _now()

    # Shift: convert UTC ts → local ts by adding the offset, then date_trunc
    offset_interval = f"{-tz_offset} minutes"  # tz_offset is getTimezoneOffset() = -localOffsetMinutes

    if period == "monthly":
        since = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        trunc = "month"
        fmt = "%Y-%m"
    elif period == "weekly":
        since = now - timedelta(weeks=12)
        trunc = "week"
        fmt = "%Y-%m-%d"
    else:  # daily (default) — last 30 days
        since = now - timedelta(days=30)
        trunc = "day"
        fmt = "%Y-%m-%d"

    from sqlalchemy import literal_column
    shifted = func.date_trunc(
        trunc,
        GuardAuditEvent.ts + literal_column(f"interval '{-tz_offset} minutes'"),
    )

    rows = (
        db.query(
            shifted.label("bucket"),
            GuardAuditEvent.ai_tool,
            func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0).label("cost"),
        )
        .filter(
            GuardAuditEvent.workspace_id.in_(org_ws),
            GuardAuditEvent.ts >= since,
            GuardAuditEvent.cost_usd_after.isnot(None),
        )
        .group_by("bucket", GuardAuditEvent.ai_tool)
        .order_by("bucket")
        .all()
    )

    # Pivot into {date, claude, codex, other} per bucket
    buckets: dict[str, dict] = {}
    for row in rows:
        label = row.bucket.strftime(fmt)
        if label not in buckets:
            buckets[label] = {"date": label, "claude": 0.0, "codex": 0.0, "other": 0.0}
        tool = (row.ai_tool or "other").lower()
        if "claude" in tool:
            buckets[label]["claude"] = round(buckets[label]["claude"] + float(row.cost), 4)
        elif "codex" in tool:
            buckets[label]["codex"] = round(buckets[label]["codex"] + float(row.cost), 4)
        else:
            buckets[label]["other"] = round(buckets[label]["other"] + float(row.cost), 4)

    return list(buckets.values())


# ── GET /guard/events/stream — SSE real-time feed ─────────────────────────────

def _fetch_new_events(workspace_id: str, since: datetime) -> tuple[list[dict], datetime]:
    """Query DB for events newer than `since`. Returns (events, new_cursor)."""
    db = SessionLocal()
    try:
        org_ws = _org_ws_subquery(db, workspace_id)
        rows = (
            db.query(GuardAuditEvent)
            .filter(
                GuardAuditEvent.workspace_id.in_(org_ws),
                GuardAuditEvent.ts > since,
            )
            .order_by(GuardAuditEvent.ts.asc())
            .limit(50)
            .all()
        )
        new_cursor = rows[-1].ts if rows else since
        return [_event_to_dict(e) for e in rows], new_cursor
    finally:
        db.close()


@router.get("/stream")
async def stream_events(
    request: Request,
    workspace_id: str | None = Query(default=None, description="Workspace ID"),
    token: str | None = Query(default=None, description="Bearer token (SSE can't set headers)"),
    db: Session = Depends(get_db),
):
    from fastapi.responses import Response as _Resp
    if not workspace_id:
        return _Resp(status_code=422, content="Provide workspace_id")

    if _clerk_enabled():
        if not token:
            return _Resp(status_code=403, content="Invalid or missing token")
        claims = _verify_clerk_token(token)
        if not claims:
            return _Resp(status_code=403, content="Invalid or missing token")
        # Verify caller is a member of the requested workspace
        user_id = claims.get("sub")
        if user_id:
            from sqlalchemy import text as _text
            is_member = db.execute(
                _text("SELECT 1 FROM workspace_users WHERE workspace_id = :ws AND clerk_user_id = :uid LIMIT 1"),
                {"ws": workspace_id, "uid": user_id},
            ).fetchone()
            if not is_member:
                return _Resp(status_code=403, content="Not a member of this workspace")

    async def event_generator():
        cursor = _now()
        deadline = asyncio.get_event_loop().time() + SSE_MAX_DURATION

        while asyncio.get_event_loop().time() < deadline:
            if await request.is_disconnected():
                break
            try:
                events, cursor = await asyncio.get_event_loop().run_in_executor(
                    None, _fetch_new_events, workspace_id, cursor
                )
                if events:
                    yield f"data: {json.dumps({'events': events})}\n\n"
            except Exception:
                yield "data: {\"error\": true}\n\n"
            await asyncio.sleep(SSE_POLL_INTERVAL)

        yield "data: {\"kind\": \"stream_timeout\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class BatchEventIn(BaseModel):
    events: list[HookEvent]


@router.post("/batch", status_code=204)
def ingest_batch(
    body: BatchEventIn,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Batch ingest from conduct-daemon audit flush. Delegates to ingest_event per item."""
    for event in body.events:
        try:
            ingest_event(event, request, background, db)
        except HTTPException:
            pass  # skip individual bad events; don't fail the whole batch


# ── Unified activity feed (#718 Phase 1B) ─────────────────────────────────────
# Reads from the `unified_activity_v` view created in migration 0028.
# UNION ALL of guard_audit_events (source='policy') and telemetry_events
# (source='tool'). Single page can render one feed with a Source filter pill.

from sqlalchemy import text as _sql_text


@router.get("/unified")
def list_unified_activity(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    source: str | None = Query(default=None, description="policy|tool"),
    status: str | None = Query(default=None, description="allowed|blocked|warned|audited|info|warning|error"),
    actor: str | None = Query(default=None, description="user_email — only matches policy rows"),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """One feed, three sources later (policy + tool today, run pending)."""
    org_ws = _org_ws_subquery(db, workspace_id)
    ws_ids = [str(r[0]) for r in org_ws.all()]

    where = ["workspace_id::text = ANY(:ws_ids)"]
    params: dict = {"ws_ids": ws_ids}
    if source:
        if source not in ("policy", "tool"):
            raise HTTPException(status_code=422, detail="source must be policy|tool")
        where.append("source = :src")
        params["src"] = source
    if status:
        where.append("status = :st")
        params["st"] = status
    if actor:
        where.append("actor = :ac")
        params["ac"] = actor
    if since:
        where.append("ts >= :since")
        params["since"] = since
    if until:
        where.append("ts <= :until")
        params["until"] = until

    sql = (
        "SELECT event_id, source, ts, actor, action, status, reason, message, session_id "
        "FROM unified_activity_v "
        "WHERE " + " AND ".join(where) + " "
        "ORDER BY ts DESC OFFSET :off LIMIT :lim"
    )
    params["off"] = offset
    params["lim"] = limit

    rows = db.execute(_sql_text(sql), params).mappings().all()
    return {
        "items": [
            {
                "event_id":   r["event_id"],
                "source":     r["source"],
                "ts":         r["ts"].isoformat() if r["ts"] else None,
                "actor":      r["actor"],
                "action":     r["action"],
                "status":     r["status"],
                "reason":     r["reason"],
                "message":    r["message"],
                "session_id": r["session_id"],
            }
            for r in rows
        ],
        "limit":  limit,
        "offset": offset,
    }


# ── Audit chain verification ───────────────────────────────────────────────────

@router.get("/audit/verify")
def verify_audit_chain(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Walk the hash chain for this workspace. Returns valid=True if unbroken.
    Only rows with entry_hash set (post-migration) are verified."""
    import uuid as _uuid
    ws_uuid = _uuid.UUID(workspace_id)

    rows = (
        db.query(GuardAuditEvent.ts, GuardAuditEvent.tool_call, GuardAuditEvent.decision,
                 GuardAuditEvent.previous_hash, GuardAuditEvent.entry_hash)
        .filter(GuardAuditEvent.workspace_id == ws_uuid, GuardAuditEvent.entry_hash.isnot(None))
        .order_by(GuardAuditEvent.ts.asc())
        .all()
    )

    if not rows:
        return {"valid": True, "total": 0, "verified_from": None, "broken_at": None}

    prev = ""
    for row in rows:
        expected = hashlib.sha256(
            f"{row.ts.isoformat()}|{row.tool_call or ''}|{row.decision}|{prev}".encode()
        ).hexdigest()
        if expected != row.entry_hash:
            return {
                "valid": False,
                "total": len(rows),
                "verified_from": rows[0].ts.isoformat(),
                "broken_at": row.ts.isoformat(),
            }
        prev = row.entry_hash

    return {
        "valid": True,
        "total": len(rows),
        "verified_from": rows[0].ts.isoformat(),
        "broken_at": None,
    }


@router.get("/correlated", tags=["guard"])
def list_correlated_events(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    decision: str | None = Query(default=None, description="blocked|warned|allowed"),
    user_email: str | None = Query(default=None),
    ai_tool: str | None = Query(default=None),
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """Audit events joined to their Guard session — groups events by session context."""
    import uuid as _uuid
    org_ws = _org_ws_subquery(db, workspace_id)

    q = (
        db.query(GuardAuditEvent, GuardSession)
        .outerjoin(GuardSession, GuardAuditEvent.session_id == GuardSession.id)
        .filter(GuardAuditEvent.workspace_id.in_(org_ws))
    )
    if decision:
        q = q.filter(GuardAuditEvent.decision == decision)
    if user_email:
        q = q.filter(GuardAuditEvent.user_email == user_email)
    if ai_tool:
        q = q.filter(GuardAuditEvent.ai_tool == ai_tool)
    if since:
        q = q.filter(GuardAuditEvent.ts >= since)
    if until:
        q = q.filter(GuardAuditEvent.ts <= until)

    rows = q.order_by(GuardAuditEvent.ts.desc()).limit(limit).all()

    # Group by session
    sessions: dict = {}
    ungrouped = []
    for event, session in rows:
        evt = {
            "id":         str(event.id),
            "ts":         event.ts.isoformat(),
            "decision":   event.decision,
            "rule_id":    event.rule_id,
            "ai_tool":    event.ai_tool,
            "tool_name":  event.tool_name if hasattr(event, "tool_name") else None,
            "user_email": event.user_email,
        }
        if session:
            sid = str(session.id)
            if sid not in sessions:
                sessions[sid] = {
                    "session_id":  sid,
                    "user_email":  session.user_email,
                    "ai_tool":     session.ai_tool,
                    "started_at":  session.started_at.isoformat() if session.started_at else None,
                    "ended_at":    session.ended_at.isoformat() if session.ended_at else None,
                    "events":      [],
                }
            sessions[sid]["events"].append(evt)
        else:
            ungrouped.append(evt)

    return {
        "sessions": list(sessions.values()),
        "ungrouped": ungrouped,
        "total": len(rows),
    }
