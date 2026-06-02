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

from app.core.auth import get_guard_org_id, _clerk_enabled, _verify_clerk_token
from app.core.database import SessionLocal, get_db
from app.modules.guard.models import GuardAuditEvent, GuardSession, GuardSpendBudget, GuardTeam, GuardMember

router = APIRouter(prefix="/guard/events", tags=["guard"])

SSE_POLL_INTERVAL = 2   # seconds between DB polls
SSE_MAX_DURATION  = 300  # reconnect after 5 min


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class HookEvent(BaseModel):
    team_id: str
    member_id: str | None = None
    session_id: str | None = None
    user_email: str | None = None
    ai_tool: str                     # claude_code | codex | cursor | copilot | windsurf | gemini
    tool_call: str                   # bash | edit | write | read
    input_summary: str | None = None
    decision: str                    # allowed | blocked | warned | approval
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


class EventOut(BaseModel):
    id: str
    team_id: str
    member_id: str | None
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

def _resolve_team_id(db: Session, team_id: str | None, workspace_id: str | None) -> str:
    """Return a concrete team_id string, or raise 422 if neither param resolves."""
    if team_id:
        return team_id
    if workspace_id:
        from app.modules.guard.routers.teams import _lookup_team
        team = _lookup_team(db, workspace_id)
        if team:
            return str(team.id)
    raise HTTPException(status_code=422, detail="Provide team_id or workspace_id")


def _event_to_dict(e: GuardAuditEvent) -> dict:
    return {
        "id": str(e.id),
        "team_id": str(e.team_id),
        "member_id": str(e.member_id) if e.member_id else None,
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


def _send_guard_slack(db: Session, team: GuardTeam, text: str) -> None:
    """Fire-and-forget Slack notification. Silently skips if not configured."""
    from app.core.crypto import decrypt
    from app.models.integration import Integration

    if not team.alert_channel or not team.workspace_id:
        return

    row = (
        db.query(Integration)
        .filter(
            Integration.workspace_id == team.workspace_id,
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
        post_message(token=token, channel=team.alert_channel, text=text)
    except Exception:
        pass  # never crash ingest on Slack failure


def _check_spend_budget(db: Session, team_id: str, team_obj: GuardTeam | None = None) -> None:
    """Log a warning (and send Slack alert) if any active budget has exceeded alert_threshold_pct."""
    now = _now()
    period_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    budgets = (
        db.query(GuardSpendBudget)
        .filter(GuardSpendBudget.team_id == team_id)
        .all()
    )
    if not budgets:
        return

    # Sum monthly cost for the team so far
    from sqlalchemy import func
    monthly_cost = (
        db.query(func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0))
        .filter(
            GuardAuditEvent.team_id == team_id,
            GuardAuditEvent.ts >= period_start,
        )
        .scalar()
    ) or 0.0

    team = team_obj or db.query(GuardTeam).filter(GuardTeam.id == team_id).first()

    for budget in budgets:
        threshold_usd = budget.monthly_limit_usd * (budget.alert_threshold_pct / 100.0)
        if monthly_cost >= threshold_usd:
            scope = f"member={budget.member_id}" if budget.member_id else "team-wide"
            log.info("guard.spend_alert", team_id=team_id, scope=scope,
                     monthly_cost_usd=round(monthly_cost, 4), threshold_usd=round(threshold_usd, 4),
                     alert_threshold_pct=budget.alert_threshold_pct, budget_usd=budget.monthly_limit_usd)
            if team and budget.monthly_limit_usd > 0 and team.notify_on_budget:
                pct_used = round((monthly_cost / budget.monthly_limit_usd) * 100)
                who = f"member={budget.member_id}" if budget.member_id else "team-wide"
                msg = (
                    f"\u26a0\ufe0f *Guard spend alert* ({who}): "
                    f"${monthly_cost:.2f} of ${budget.monthly_limit_usd:.2f} used ({pct_used}%) \u2014 "
                    f"alert threshold {budget.alert_threshold_pct}% reached"
                )
                _send_guard_slack(db, team, msg)


# ── POST /guard/events — ingest ───────────────────────────────────────────────

@router.post("", response_model=EventOut, status_code=201)
def ingest_event(
    body: HookEvent,
    db: Session = Depends(get_db),
):
    """Ingest a hook event from the guardctl binary. No workspace auth — teams
    authenticate via team_id embedded in the hook payload."""
    # Validate team exists
    team = db.query(GuardTeam).filter(GuardTeam.id == body.team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="team_id not found")

    now = _now()

    # 1. Write the audit event
    event = GuardAuditEvent(
        team_id=body.team_id,
        member_id=body.member_id,
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

    db.commit()
    db.refresh(event)

    # 3. Send Slack block/warn notification (non-fatal)
    try:
        if body.decision in ("blocked", "warned") and team.notify_on_block:
            who = body.user_email or body.member_id or "unknown"
            emoji = "\U0001f6ab" if body.decision == "blocked" else "\u26a0\ufe0f"
            rule_label = f"`{body.rule_id}`" if body.rule_id else "a policy"
            msg = f"{emoji} *{who}* {body.decision} by {rule_label} in {body.ai_tool or 'Claude Code'}"
            if body.rule_message:
                msg += f"\n> {body.rule_message}"
            _send_guard_slack(db, team, msg)
    except Exception as exc:
        log.warning("guard.slack_notification_failed", exc=str(exc))

    # 4. Check spend budget (non-fatal — log + Slack)
    try:
        _check_spend_budget(db, body.team_id, team_obj=team)
    except Exception as exc:
        log.warning("guard.spend_budget_check_failed", exc=str(exc))

    return EventOut(**_event_to_dict(event))


# ── GET /guard/events — paginated list ────────────────────────────────────────

@router.get("", response_model=list[EventOut])
def list_events(
    db: Session = Depends(get_db),
    _org_id: str = Depends(get_guard_org_id),
    team_id: str | None = Query(default=None, description="Team ID to filter by"),
    workspace_id: str | None = Query(default=None, description="Workspace ID (alternative to team_id)"),
    decision: str | None = Query(default=None, description="allowed|blocked|warned|approval"),
    ai_tool: str | None = Query(default=None, description="claude_code|codex|cursor|copilot|windsurf|gemini"),
    user_email: str | None = Query(default=None),
    since: datetime | None = Query(default=None, description="ISO datetime lower bound"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    """Paginated, filterable audit event list for a team."""
    resolved = _resolve_team_id(db, team_id, workspace_id)
    q = (
        db.query(GuardAuditEvent)
        .filter(GuardAuditEvent.team_id == resolved)
    )
    if decision:
        q = q.filter(GuardAuditEvent.decision == decision)
    if ai_tool:
        q = q.filter(GuardAuditEvent.ai_tool == ai_tool)
    if user_email:
        q = q.filter(GuardAuditEvent.user_email == user_email)
    if since:
        q = q.filter(GuardAuditEvent.ts >= since)

    rows = (
        q.order_by(GuardAuditEvent.ts.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [EventOut(**_event_to_dict(e)) for e in rows]


# ── GET /guard/events/stream — SSE real-time feed ─────────────────────────────

def _fetch_new_events(team_id: str, since: datetime) -> tuple[list[dict], datetime]:
    """Query DB for events newer than `since`. Returns (events, new_cursor)."""
    db = SessionLocal()
    try:
        rows = (
            db.query(GuardAuditEvent)
            .filter(
                GuardAuditEvent.team_id == team_id,
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
    team_id: str | None = Query(default=None, description="Team ID"),
    workspace_id: str | None = Query(default=None, description="Workspace ID (alternative to team_id)"),
    token: str | None = Query(default=None, description="Bearer token (SSE can't set headers)"),
):
    if _clerk_enabled():
        if not token or not _verify_clerk_token(token):
            from fastapi.responses import Response
            return Response(status_code=403, content="Invalid or missing token")
    # Resolve team_id from workspace_id if needed
    if not team_id and workspace_id:
        db_sess = SessionLocal()
        try:
            from app.modules.guard.routers.teams import _lookup_team
            team = _lookup_team(db_sess, workspace_id)
            if team:
                team_id = str(team.id)
        finally:
            db_sess.close()
    if not team_id:
        from fastapi.responses import Response
        return Response(status_code=422, content="Provide team_id or workspace_id")

    async def event_generator():
        cursor = _now()
        deadline = asyncio.get_event_loop().time() + SSE_MAX_DURATION

        while asyncio.get_event_loop().time() < deadline:
            if await request.is_disconnected():
                break
            try:
                events, cursor = await asyncio.get_event_loop().run_in_executor(
                    None, _fetch_new_events, team_id, cursor
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
