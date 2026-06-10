"""
POST /guard/events          — ingest hook event (called by guardctl binary)
GET  /guard/events          — paginated list, filterable
GET  /guard/events/stream   — SSE real-time feed
"""
import asyncio
import json
from datetime import datetime, timezone

import structlog

log = structlog.get_logger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, _clerk_enabled, _verify_clerk_token
from app.core.database import SessionLocal, get_db
from app.modules.guard.models import GuardAuditEvent, GuardConfig, GuardSession, GuardSpendBudget

router = APIRouter(prefix="/guard/events", tags=["guard"])

SSE_POLL_INTERVAL = 2    # seconds between DB polls
SSE_MAX_DURATION  = 300  # reconnect after 5 min


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class HookEvent(BaseModel):
    workspace_id: str
    clerk_user_id: str | None = None
    session_id: str | None = None
    user_email: str | None = None
    ai_tool: str                      # claude_code | codex | cursor | copilot | windsurf | gemini
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


class UsageUpdate(BaseModel):
    workspace_id: str
    hook_session_id: str
    tool_name: str | None = None
    tokens_input: int
    tokens_output: int
    duration_ms: int | None = None
    ai_tool: str | None = None   # for pricing


class UsageOut(BaseModel):
    updated: bool


class EventOut(BaseModel):
    id: str
    workspace_id: str
    clerk_user_id: str | None
    session_id: str | None
    user_email: str | None
    ai_tool: str
    tool_call: str
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
    duration_ms: int | None
    ts: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _event_to_dict(e: GuardAuditEvent) -> dict:
    return {
        "id": str(e.id),
        "workspace_id": str(e.workspace_id),
        "clerk_user_id": e.clerk_user_id,
        "session_id": str(e.session_id) if e.session_id else None,
        "user_email": e.user_email,
        "ai_tool": e.ai_tool,
        "tool_call": e.tool_call,
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
        "duration_ms": e.duration_ms,
        "ts": e.ts.isoformat(),
    }


def _send_guard_slack(db: Session, config: GuardConfig, text_msg: str) -> None:
    """Fire-and-forget Slack notification. Silently skips if not configured."""
    from app.core.crypto import decrypt
    from app.models.integration import Integration

    if not config.alert_channel:
        return

    row = (
        db.query(Integration)
        .filter(
            Integration.workspace_id == config.workspace_id,
            Integration.handle == "slack",
        )
        .first()
    )
    if not row or not row.encrypted_credentials:
        return

    try:
        creds = decrypt(row.encrypted_credentials)
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

@router.post("", response_model=EventOut, status_code=201)
def ingest_event(
    body: HookEvent,
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

    # 1. Write the audit event
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
        ts=now,
    )
    db.add(event)
    db.flush()  # get event.id before commit

    # 2. Update GuardSession totals if session_id provided
    if body.session_id:
        session = (
            db.query(GuardSession)
            .filter(GuardSession.id == body.session_id)
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

    db.flush()
    db.refresh(event)

    # 3. Send Slack block/warn notification (non-fatal)
    try:
        if body.decision in ("blocked", "warned") and config.notify_on_block:
            who = body.user_email or body.clerk_user_id or "unknown"
            tool = body.ai_tool or "Claude Code"
            rule_label = f"`{body.rule_id}`" if body.rule_id else "a policy"
            if body.rule_id == "budget-hard-cap":
                header_emoji = "\U0001f6a8"
                decision_label = "BUDGET CAP HIT"
            elif body.decision == "blocked":
                header_emoji = "\U0001f6a8"   # 🚨
                decision_label = "BLOCKED"
            else:
                header_emoji = "\u26a0\ufe0f"  # ⚠️
                decision_label = "WARNED"
            msg = (
                f"{header_emoji} *{decision_label}* by {rule_label} in {tool}\n"
                f"\U0001f464 *Developer:* {who}"
            )
            if body.rule_message:
                msg += f"\n\U0001f4ac {body.rule_message}"
            _send_guard_slack(db, config, msg)
    except Exception as exc:
        log.warning("guard.slack_notification_failed", exc=str(exc))

    # 4. Check spend budget (non-fatal — log + Slack)
    try:
        _check_spend_budget(db, body.workspace_id, config=config)
    except Exception as exc:
        log.warning("guard.spend_budget_check_failed", exc=str(exc))

    # 5. Trigger Security Loop scan on block (automation_security_scan toggle)
    if body.decision == "blocked" and config.automation_security_scan:
        try:
            from app.routers.security import FindingIn, _ingest_finding_core, _trigger_security_loop
            scan_body = FindingIn(
                tool=body.ai_tool or "claude_code",
                severity="medium",
                type="guard_violation",
                description=f"Guard blocked: {body.rule_message or body.rule_id or 'policy violation'}",
                reporter_email=body.user_email,
            )
            sec_finding = _ingest_finding_core(scan_body, body.workspace_id, db)
            _trigger_security_loop(sec_finding, body.workspace_id, db)
            # Also check automation workflow threshold (Connection 2)
            from app.routers.security import _maybe_trigger_automation_workflow
            _maybe_trigger_automation_workflow(sec_finding, body.workspace_id, db)
            log.info("guard.violation_security_scan_triggered", event_id=str(event.id), finding_id=str(sec_finding.id))
        except Exception as exc:
            log.warning("guard.violation_security_scan_failed", error=str(exc))

    db.commit()
    return EventOut(**_event_to_dict(event))


# ── POST /guard/events/usage — PostToolUse token backfill ────────────────────

TOOL_PRICING = {
    "claude-code": {"input": 3.0,  "output": 15.0},
    "codex":       {"input": 2.5,  "output": 10.0},
    "cursor":      {"input": 3.0,  "output": 15.0},
    "windsurf":    {"input": 3.0,  "output": 15.0},
    "unknown":     {"input": 3.0,  "output": 15.0},
}


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
    pricing = TOOL_PRICING.get(tool_key, TOOL_PRICING["unknown"])
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

    db.commit()

    return UsageOut(updated=True)


# ── GET /guard/events — paginated list ────────────────────────────────────────

@router.get("", response_model=list[EventOut])
def list_events(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    decision: str | None = Query(default=None, description="allowed|blocked|warned|approval"),
    ai_tool: str | None = Query(default=None, description="claude_code|codex|cursor|copilot|windsurf|gemini"),
    user_email: str | None = Query(default=None),
    since: datetime | None = Query(default=None, description="ISO datetime lower bound"),
    until: datetime | None = Query(default=None, description="ISO datetime upper bound"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Paginated, filterable audit event list for a workspace."""
    import uuid
    ws_uuid = uuid.UUID(workspace_id)

    q = db.query(GuardAuditEvent).filter(GuardAuditEvent.workspace_id == ws_uuid)
    if decision:
        q = q.filter(GuardAuditEvent.decision == decision)
    if ai_tool:
        q = q.filter(GuardAuditEvent.ai_tool == ai_tool)
    if user_email:
        q = q.filter(GuardAuditEvent.user_email == user_email)
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
    import uuid
    from datetime import timedelta
    from sqlalchemy import func, text as _text

    ws_uuid = uuid.UUID(workspace_id)
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
            GuardAuditEvent.workspace_id == ws_uuid,
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
    import uuid
    ws_uuid = uuid.UUID(workspace_id)
    db = SessionLocal()
    try:
        rows = (
            db.query(GuardAuditEvent)
            .filter(
                GuardAuditEvent.workspace_id == ws_uuid,
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
