"""ConductGuard spend — summary and sessions endpoints (GET /guard/spend, /guard/spend/sessions)."""

import time
from datetime import timedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.core.keyset import before_clause
from app.modules.guard.models import GuardAuditEvent, GuardDeveloperTools, GuardSession
import structlog as _structlog
from app.modules.guard.routers.spend_common import (
    DeveloperSpend,
    ModelSpend,
    ProviderSpend,
    SessionOut,
    SpendSummary,
    ToolSpend,
    _current_period_start,
    _next_period_start,
    _now,
    _org_ws_subquery,
    _parse_period_start,
    _period_label,
)

router = APIRouter(prefix="/guard/spend", tags=["guard"])


_log = _structlog.get_logger("app.modules.guard.routers.spend")

# ponytail: per-process TTL cache; each worker warms its own. Move to Redis if
# workers scale out and the extra cold misses show up.
_SUMMARY_TTL_S = 60          # current month: numbers move, 60s stale is fine
_PAST_SUMMARY_TTL_S = 3600   # closed months barely change
_summary_cache: dict[tuple[str, str], tuple[float, SpendSummary]] = {}


@router.get("", response_model=SpendSummary)
def get_spend_summary(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    month: str | None = Query(default=None, description="Period in YYYY-MM format; defaults to current month"),
):
    """Spend summary for a workspace for the given month (defaults to current calendar month)."""
    period = _parse_period_start(month).strftime("%Y-%m")  # normalise so bad input shares the fallback entry
    key = (workspace_id, period)
    hit = _summary_cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    try:
        summary = _get_spend_summary_inner(db, workspace_id, month)
    except OperationalError as exc:
        _log.error("guard.spend_summary_error", workspace_id=workspace_id, exc=str(exc), exc_info=True)
        return SpendSummary(
            workspace_id=workspace_id,
            period=month or _period_label(),
            active_developers=0,
            events_today=0,
            blocked_today=0,
            tokens_saved_today=0,
            total_tokens_before=0,
            total_tokens_after=0,
            total_saved_pct=0,
            total_cost_usd=0.0,
            total_saved_usd=0.0,
            sessions=0,
            hook_sessions=0,
            by_developer=[],
            by_ai_tool=[],
            by_model=[],
            by_provider=[],
        )
    if len(_summary_cache) > 1000:
        _summary_cache.clear()
    ttl = _SUMMARY_TTL_S if period == _period_label() else _PAST_SUMMARY_TTL_S
    _summary_cache[key] = (time.monotonic() + ttl, summary)
    return summary


def _get_spend_summary_inner(db: Session, workspace_id: str, month: str | None) -> "SpendSummary":
    now = _now()
    period_start = _parse_period_start(month)
    period_end = _next_period_start(period_start)
    is_current_month = period_start == _current_period_start()
    org_ws = _org_ws_subquery(db, workspace_id)

    # Aggregate totals
    totals = (
        db.query(
            func.coalesce(func.sum(GuardAuditEvent.tokens_before), 0).label("tokens_before"),
            func.coalesce(func.sum(GuardAuditEvent.tokens_after), 0).label("tokens_after"),
            func.coalesce(func.sum(GuardAuditEvent.cost_usd_before), 0.0).label("cost_before"),
            func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0).label("cost_after"),
        )
        .filter(
            GuardAuditEvent.workspace_id.in_(org_ws),
            GuardAuditEvent.ts >= period_start,
            GuardAuditEvent.ts < period_end,
        )
        .one()
    )

    total_tokens_before = int(totals.tokens_before)
    total_tokens_after = int(totals.tokens_after)
    total_cost_usd = float(totals.cost_after)
    total_saved_usd = float(totals.cost_before) - float(totals.cost_after)
    total_saved_pct = (
        round((1 - total_tokens_after / total_tokens_before) * 100)
        if total_tokens_before > 0
        else 0
    )

    # By developer
    dev_rows = (
        db.query(
            GuardAuditEvent.user_email,
            func.coalesce(func.sum(GuardAuditEvent.tokens_after), 0).label("tokens_after"),
            func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0).label("cost_usd"),
            func.coalesce(func.sum(GuardAuditEvent.cost_usd_before) - func.sum(GuardAuditEvent.cost_usd_after), 0.0).label("saved_usd"),
        )
        .filter(
            GuardAuditEvent.workspace_id.in_(org_ws),
            GuardAuditEvent.ts >= period_start,
            GuardAuditEvent.ts < period_end,
            GuardAuditEvent.user_email.isnot(None),
        )
        .group_by(GuardAuditEvent.user_email)
        .order_by(func.sum(GuardAuditEvent.cost_usd_after).desc())
        .all()
    )

    # Session counts per developer
    session_counts: dict[str, int] = {}
    session_rows = (
        db.query(GuardSession.user_email, func.count(GuardSession.id))
        .filter(
            GuardSession.workspace_id.in_(org_ws),
            GuardSession.started_at >= period_start,
            GuardSession.started_at < period_end,
            GuardSession.user_email.isnot(None),
        )
        .group_by(GuardSession.user_email)
        .all()
    )
    for email, cnt in session_rows:
        if email:
            session_counts[email] = cnt

    # Tool coverage per developer (latest snapshot, keyed by email)
    # guard_developer_tools.workspace_id is Text; org_ws returns UUIDs — must cast to str
    _ws_strs = [str(r[0]) for r in org_ws.all()]
    tool_coverage: dict[str, GuardDeveloperTools] = {}
    coverage_rows = (
        db.query(GuardDeveloperTools)
        .filter(GuardDeveloperTools.workspace_id.in_(_ws_strs))
        .all()
    )
    for tc in coverage_rows:
        tool_coverage[tc.user_email] = tc

    by_developer = [
        DeveloperSpend(
            email=row.user_email,
            tokens_after=int(row.tokens_after),
            cost_usd=round(float(row.cost_usd), 6),
            saved_usd=round(float(row.saved_usd), 6),
            sessions=session_counts.get(row.user_email, 0),
            detected_tools=tool_coverage[row.user_email].detected_tools or [] if row.user_email in tool_coverage else [],
            mcp_registered=tool_coverage[row.user_email].mcp_registered or [] if row.user_email in tool_coverage else [],
            hook_registered=tool_coverage[row.user_email].hook_registered or [] if row.user_email in tool_coverage else [],
        )
        for row in dev_rows
    ]

    # By AI tool
    # tokens_after = actually consumed; tokens_saved = prevented exposure
    # (tokens_before - tokens_after, treating NULL as 0). Surfaces Guard's
    # value on blocked events without inflating the "used" column.
    tool_rows = (
        db.query(
            GuardAuditEvent.ai_tool,
            func.coalesce(func.sum(GuardAuditEvent.tokens_after), 0).label("tokens_after"),
            func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0).label("cost_usd"),
            func.coalesce(func.sum(func.coalesce(GuardAuditEvent.tokens_before, 0) - func.coalesce(GuardAuditEvent.tokens_after, 0)), 0).label("tokens_saved"),
            func.coalesce(func.sum(func.coalesce(GuardAuditEvent.cost_usd_before, 0.0) - func.coalesce(GuardAuditEvent.cost_usd_after, 0.0)), 0.0).label("cost_saved"),
        )
        .filter(
            GuardAuditEvent.workspace_id.in_(org_ws),
            GuardAuditEvent.ts >= period_start,
            GuardAuditEvent.ts < period_end,
        )
        .group_by(GuardAuditEvent.ai_tool)
        .order_by(func.sum(GuardAuditEvent.cost_usd_after).desc())
        .all()
    )

    by_ai_tool = [
        ToolSpend(
            ai_tool=row.ai_tool,
            tokens_after=int(row.tokens_after),
            cost_usd=round(float(row.cost_usd), 6),
            tokens_saved=int(row.tokens_saved),
            cost_saved=round(float(row.cost_saved), 6),
        )
        for row in tool_rows
    ]

    # by_model / by_provider — only rows that actually carry a model/provider
    # (i.e. proxy-flowing audit events). Hook rows are excluded so the "cost
    # by model" view stays honest and comparable across workspaces.
    model_rows = (
        db.query(
            GuardAuditEvent.provider.label("provider"),
            GuardAuditEvent.model.label("model"),
            func.coalesce(func.sum(func.coalesce(GuardAuditEvent.tokens_after, 0)), 0).label("tokens_after"),
            func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0).label("cost_usd"),
        )
        .filter(
            GuardAuditEvent.workspace_id.in_(org_ws),
            GuardAuditEvent.ts >= period_start,
            GuardAuditEvent.ts < period_end,
            GuardAuditEvent.model.isnot(None),
            GuardAuditEvent.provider.isnot(None),
        )
        .group_by(GuardAuditEvent.provider, GuardAuditEvent.model)
        .order_by(func.sum(GuardAuditEvent.cost_usd_after).desc())
        .all()
    )
    by_model = [
        ModelSpend(
            provider=row.provider,
            model=row.model,
            tokens_after=int(row.tokens_after),
            cost_usd=round(float(row.cost_usd), 6),
        )
        for row in model_rows
    ]

    provider_rows = (
        db.query(
            GuardAuditEvent.provider.label("provider"),
            func.coalesce(func.sum(func.coalesce(GuardAuditEvent.tokens_after, 0)), 0).label("tokens_after"),
            func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0).label("cost_usd"),
        )
        .filter(
            GuardAuditEvent.workspace_id.in_(org_ws),
            GuardAuditEvent.ts >= period_start,
            GuardAuditEvent.ts < period_end,
            GuardAuditEvent.provider.isnot(None),
        )
        .group_by(GuardAuditEvent.provider)
        .order_by(func.sum(GuardAuditEvent.cost_usd_after).desc())
        .all()
    )
    by_provider = [
        ProviderSpend(
            provider=row.provider,
            tokens_after=int(row.tokens_after),
            cost_usd=round(float(row.cost_usd), 6),
        )
        for row in provider_rows
    ]

    # "Today" fields = rolling 24h for the current month; whole selected
    # month otherwise. Keeps the dashboard "today" meaning intact while making
    # past-month views internally consistent with the other totals.
    today_start = now - timedelta(hours=24) if is_current_month else period_start
    today_end = now if is_current_month else period_end
    events_today = int(
        db.query(func.count(GuardAuditEvent.id))
        .filter(
            GuardAuditEvent.workspace_id.in_(org_ws),
            GuardAuditEvent.ts >= today_start,
            GuardAuditEvent.ts < today_end,
        )
        .scalar() or 0
    )
    blocked_today = int(
        db.query(func.count(GuardAuditEvent.id))
        .filter(
            GuardAuditEvent.workspace_id.in_(org_ws),
            GuardAuditEvent.ts >= today_start,
            GuardAuditEvent.ts < today_end,
            GuardAuditEvent.decision == "blocked",
        )
        .scalar() or 0
    )
    tokens_saved_today = int(
        db.query(func.coalesce(
            func.sum(GuardAuditEvent.tokens_before - GuardAuditEvent.tokens_after), 0
        ))
        .filter(
            GuardAuditEvent.workspace_id.in_(org_ws),
            GuardAuditEvent.ts >= today_start,
            GuardAuditEvent.ts < today_end,
            GuardAuditEvent.tokens_before.isnot(None),
            GuardAuditEvent.tokens_after.isnot(None),
        )
        .scalar() or 0
    )

    # Count distinct developers who opened a Guard session in the period
    org_ws_ids = _ws_strs  # already materialized above for tool_coverage
    active_developers = int(db.execute(
        text("""
            SELECT COUNT(DISTINCT COALESCE(user_email, clerk_user_id))
            FROM guard_sessions
            WHERE workspace_id::text = ANY(:ws_ids)
              AND started_at >= :since
              AND started_at <  :until
              AND (user_email IS NOT NULL OR clerk_user_id IS NOT NULL)
        """),
        {"ws_ids": org_ws_ids, "since": period_start, "until": period_end},
    ).scalar() or 0)

    # Proxy session count (guard_sessions rows)
    sessions_count = int(
        db.query(func.count(GuardSession.id))
        .filter(
            GuardSession.workspace_id.in_(org_ws),
            GuardSession.started_at >= period_start,
            GuardSession.started_at <  period_end,
        )
        .scalar() or 0
    )

    # Direct hook session count — distinct sessions in the 24h window.
    # Use hook_session_id when available (Claude Code sets it); fall back to
    # coalescing with ai_tool+user_email so Codex events (which may omit
    # session_id in hook stdin) still count.
    # hook_session_id is set by CC/Codex hooks; proxy events never set it.
    # Can't use session_id.is_(None) — the events router now auto-creates a
    # GuardSession for hook events, so session_id is always non-NULL.
    hook_sessions_count = int(
        db.query(func.count(func.distinct(GuardAuditEvent.hook_session_id)))
        .filter(
            GuardAuditEvent.workspace_id.in_(org_ws),
            GuardAuditEvent.hook_session_id.isnot(None),
            GuardAuditEvent.ts >= today_start,
            GuardAuditEvent.ts <  today_end,
        )
        .scalar() or 0
    )

    return SpendSummary(
        workspace_id=workspace_id,
        period=month or _period_label(),
        active_developers=active_developers,
        events_today=events_today,
        blocked_today=blocked_today,
        tokens_saved_today=tokens_saved_today,
        total_tokens_before=total_tokens_before,
        total_tokens_after=total_tokens_after,
        total_saved_pct=total_saved_pct,
        total_cost_usd=round(total_cost_usd, 6),
        total_saved_usd=round(total_saved_usd, 6),
        sessions=sessions_count,
        hook_sessions=hook_sessions_count,
        by_developer=by_developer,
        by_ai_tool=by_ai_tool,
        by_model=by_model,
        by_provider=by_provider,
    )


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    workspace_id: str = Depends(get_workspace_id),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    before: str | None = Query(default=None, description="Keyset cursor '<started_at>|<id>' from the last row ('|<id>' when started_at is null); wins over offset"),
    db: Session = Depends(get_db),
):
    """List sessions with cumulative spend totals."""
    org_ws = _org_ws_subquery(db, workspace_id)
    q = db.query(GuardSession).filter(GuardSession.workspace_id.in_(org_ws))
    cursor = before_clause(GuardSession.started_at, GuardSession.id, before, nulls_last=True)
    if cursor is not None:
        q, offset = q.filter(cursor), 0
    rows = (
        q.order_by(GuardSession.started_at.desc().nulls_last(), GuardSession.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        SessionOut(
            id=str(s.id),
            workspace_id=str(s.workspace_id),
            clerk_user_id=s.clerk_user_id,
            user_email=s.user_email,
            ai_tool=s.ai_tool,
            started_at=s.started_at.isoformat() if s.started_at else None,
            ended_at=s.ended_at.isoformat() if s.ended_at else None,
            total_tokens_before=s.total_tokens_before,
            total_tokens_after=s.total_tokens_after,
            total_cost_usd=s.total_cost_usd,
            total_saved_usd=s.total_saved_usd,
            event_count=s.event_count,
            violations_count=s.violations_count,
            client_ip=s.client_ip,
            os_info=s.os_info,
            hostname=s.hostname,
            intent=s.intent,
            session_parse_status=s.session_parse_status,
        )
        for s in rows
    ]
