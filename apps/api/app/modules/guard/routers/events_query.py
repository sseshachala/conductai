"""ConductGuard events — read/query endpoints (list, rule fires, cost trend, SSE stream, batch, unified, audit verify, correlated)."""

import asyncio
import hashlib
import json
from datetime import datetime
from uuid import UUID
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.core.auth import (
    get_workspace_id,
    get_user_id,
    require_permission,
)
from app.core.stream_auth import stream_credentials
from app.core.database import SessionLocal, get_db
from app.core.pii import redact_secrets
from app.modules.guard.models import GuardAuditEvent, GuardSession
from sqlalchemy import text as _sql_text
from app.modules.guard.routers.events_common import (
    BatchEventIn,
    EventOut,
    RuleFireOut,
    SSE_MAX_DURATION,
    SSE_POLL_INTERVAL,
    _end_of_day_if_bare,
    _event_to_dict,
    _now,
    _org_ws_subquery,
)
from app.modules.guard.routers.events_ingest import (
    _authenticated_workspace_uuid,
    _hook_authenticated_workspace,
    ingest_event,
)

router = APIRouter(prefix="/guard/events", tags=["guard"])


@router.get("/session-usage/{event_id}/reconciliation")
def session_reconciliation(
    event_id: UUID,
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _permission: str = Depends(require_permission("guard.spend.view_own")),
    db: Session = Depends(get_db),
):
    from app.modules.guard.event_access import restrict_event_query
    from app.modules.guard.session_reconciliation import session_evidence

    event = restrict_event_query(db.query(GuardAuditEvent), db, workspace_id, user_id,
                                 event_id, permission_area="spend").first()
    if event is None or event.tool_call != "session_usage" or not (event.routing_meta or {}).get("session_usage"):
        raise HTTPException(status_code=404, detail="Session usage not found")
    try:
        UUID(event.hook_session_id)
    except (ValueError, TypeError, AttributeError):
        raise HTTPException(status_code=409, detail="Session identifier unavailable") from None
    if not event.clerk_user_id and not event.agent_identity_id:
        raise HTTPException(status_code=409, detail="Session actor unavailable")
    return session_evidence(db, event)


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
    hook_session_id: str | None = Query(default=None),
    agent_identity_id: str | None = Query(default=None),
    event_id: UUID | None = Query(default=None),
    user_id: str = Depends(get_user_id),
):
    """Paginated, filterable audit event list for a workspace."""
    org_ws = _org_ws_subquery(db, workspace_id)

    q = db.query(GuardAuditEvent).filter(GuardAuditEvent.workspace_id.in_(org_ws))
    if isinstance(event_id, UUID):
        from app.modules.guard.event_access import restrict_event_query
        q = restrict_event_query(q, db, workspace_id, user_id, event_id)
    if hook_session_id:
        q = q.filter(GuardAuditEvent.hook_session_id == hook_session_id)
    if agent_identity_id:
        q = q.filter(GuardAuditEvent.agent_identity_id == agent_identity_id)
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
        q = q.filter(GuardAuditEvent.ts <= _end_of_day_if_bare(until))

    rows = (
        q.order_by(GuardAuditEvent.ts.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [EventOut(**_event_to_dict(e)) for e in rows]


def _project_rule_fire(e: GuardAuditEvent) -> RuleFireOut:
    """Property 9: redact input_summary via app.core.pii.redact_secrets
    before it leaves the API. Emit only a hash prefix + size for dedupe."""
    raw = e.input_summary or ""
    redacted_text, _found = redact_secrets(raw) if raw else ("", [])
    return RuleFireOut(
        id=str(e.id),
        ts=e.ts.isoformat() if e.ts else "",
        rule_id=e.rule_id,
        decision=e.decision,
        tool_call=e.tool_call,
        source=e.source or "hook",
        ai_tool=e.ai_tool,
        input_summary_redacted=redacted_text or None,
        input_hash_prefix=(
            hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()[:16]
            if raw else None
        ),
        input_size_bytes=len(raw.encode("utf-8", errors="replace")),
    )


@router.get("/rule/{rule_id}/fires", response_model=list[RuleFireOut])
def list_rule_fires(
    rule_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    limit: int = Query(default=20, ge=1, le=100),
    _: str = Depends(require_permission("guard.activity.view_own")),
):
    """#1755 Slice 2 — Recent Firings panel for a specific rule.

    Returns the most recent N events that fired ``rule_id`` in this
    workspace, projected through ``redact_secrets`` so raw input_summary
    never leaves the API. Hash prefix + size ride along for dedupe /
    volume signals without needing the payload.
    """
    org_ws = _org_ws_subquery(db, workspace_id)
    rows = (
        db.query(GuardAuditEvent)
        .filter(
            GuardAuditEvent.workspace_id.in_(org_ws),
            GuardAuditEvent.rule_id == rule_id,
        )
        .order_by(GuardAuditEvent.ts.desc())
        .limit(limit)
        .all()
    )
    return [_project_rule_fire(e) for e in rows]


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
    from sqlalchemy import func

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


# SSE cursor type: (ts, id). Keyset pagination — deterministic strict
# ordering so rows at the same wallclock never span a poll boundary
# (#1990 item A). Nil id used as the lower bound on the initial cursor.
_SSE_NIL_UUID = "00000000-0000-0000-0000-000000000000"


def _fetch_new_events(
    workspace_id: str,
    since: tuple[datetime, str],
) -> tuple[list[dict], tuple[datetime, str]]:
    """Query DB for events past the cursor. Returns (events, new_cursor).

    Uses a single monotonic key: GREATEST(ts, finalized_at). Rows are
    ordered by (key, id) with the cursor advancing on the same key. This
    ensures the query and the cursor agree on ordering — no newer rows
    can be skipped because a late finalize on an old row shifted the
    boundary (P1 review finding 5).

    Rows are re-emitted with the new key when their finalized_at moves
    past the previous key — the frontend's merge-by-id SSE handler
    (#1986 Phase 3) dedupes them into the same row, updating the
    lifecycle pill in place.
    """
    from sqlalchemy import and_, or_, func
    since_key, since_id = since
    db = SessionLocal()
    try:
        org_ws = _org_ws_subquery(db, workspace_id)
        # GREATEST(ts, COALESCE(finalized_at, ts)) — one expression for both
        # ordering and filtering so the query cannot disagree with the
        # cursor about what "next" means.
        activity_key = func.greatest(
            GuardAuditEvent.ts,
            func.coalesce(GuardAuditEvent.finalized_at, GuardAuditEvent.ts),
        )
        rows = (
            db.query(GuardAuditEvent)
            .filter(
                GuardAuditEvent.workspace_id.in_(org_ws),
                or_(
                    activity_key > since_key,
                    and_(
                        activity_key == since_key,
                        GuardAuditEvent.id > since_id,
                    ),
                ),
            )
            .order_by(activity_key.asc(), GuardAuditEvent.id.asc())
            .limit(50)
            .all()
        )
        if not rows:
            return [], since
        # Cursor advances on the same monotonic key the query used.
        def _key(r):
            return max(r.ts, r.finalized_at or r.ts)
        newest_row = max(rows, key=lambda r: (_key(r), str(r.id)))
        return (
            [_event_to_dict(e) for e in rows],
            (_key(newest_row), str(newest_row.id)),
        )
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

    workspace_id = get_workspace_id(
        credentials=stream_credentials(request), ws_id=workspace_id,
        x_workspace_id=None, db=db,
    )

    async def event_generator():
        cursor: tuple[datetime, str] = (_now(), _SSE_NIL_UUID)
        deadline = asyncio.get_event_loop().time() + SSE_MAX_DURATION

        while asyncio.get_event_loop().time() < deadline:
            if await request.is_disconnected():
                break
            try:
                events, cursor = await asyncio.get_event_loop().run_in_executor(
                    None, _fetch_new_events, workspace_id, cursor
                )
                if events:
                    # Include server_time on every payload — the client
                    # uses the drift between this and its Date.now() to
                    # correct LifecyclePill's client-side 'expired'
                    # detection (#1990 item D). Cheap, one ISO string.
                    payload = {
                        "events": events,
                        "server_time": _now().isoformat(),
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
            except Exception:
                yield "data: {\"error\": true}\n\n"
            await asyncio.sleep(SSE_POLL_INTERVAL)

        yield "data: {\"kind\": \"stream_timeout\"}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/batch", status_code=204)
def ingest_batch(
    body: BatchEventIn,
    request: Request,
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    auth_context: tuple[str, str | None] | None = Depends(_hook_authenticated_workspace),
):
    """Batch ingest from conduct-daemon audit flush. Delegates to ingest_event per item."""
    for event in body.events:
        _authenticated_workspace_uuid(event.workspace_id, auth_context)
    for event in body.events:
        try:
            ingest_event(event, request, background, db, auth_context)
        except HTTPException:
            pass  # skip individual bad events; don't fail the whole batch


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
        where.append("ts <= :until")  # note: caller should end-of-day normalise; TODO
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


@router.get("/audit/verify")
def verify_audit_chain(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Authenticate archived boundaries, then verify the retained chain."""
    from app.modules.guard.audit_retention import verify_audit_history
    result = verify_audit_history(db, workspace_id)
    return {key: result[key] for key in ("valid", "total", "verified_from", "broken_at")}


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
        q = q.filter(GuardAuditEvent.ts <= _end_of_day_if_bare(until))

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
