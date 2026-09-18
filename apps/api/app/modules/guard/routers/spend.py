"""
GET  /guard/spend                  — spend summary for workspace (current calendar month)
GET  /guard/spend/sessions         — list sessions with totals
POST /guard/spend/budgets          — create or update a budget for user or workspace-wide
GET  /guard/spend/budgets          — list all budgets with current month usage
GET  /guard/spend/budget-check     — hard-cap check called by the guard hook (no Clerk auth)
"""
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, distinct, or_, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from fastapi import HTTPException
from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.models.workspace import Workspace
from app.modules.guard.models import BudgetReservation, GuardAuditEvent, GuardConfig, GuardDeveloperTools, GuardSession, GuardSpendBudget

router = APIRouter(prefix="/guard/spend", tags=["guard"])


def _org_ws_subquery(db: Session, workspace_id: str):
    """Strict single-workspace scoping. See issue #1564."""
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return db.query(Workspace.id).filter(Workspace.id == None)  # noqa: E711 — safe empty subquery
    return db.query(Workspace.id).filter(Workspace.id == ws_uuid)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _current_period_start() -> datetime:
    now = _now()
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _period_label() -> str:
    now = _now()
    return now.strftime("%Y-%m")


def _parse_period_start(month: str | None) -> datetime:
    """Parse 'YYYY-MM' into period start datetime. Falls back to current month."""
    if month:
        try:
            return datetime.strptime(month, "%Y-%m").replace(
                tzinfo=timezone.utc, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        except ValueError:
            pass
    return _current_period_start()


def _next_period_start(period_start: datetime) -> datetime:
    """First instant of the calendar month after period_start."""
    if period_start.month == 12:
        return period_start.replace(year=period_start.year + 1, month=1)
    return period_start.replace(month=period_start.month + 1)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class DeveloperSpend(BaseModel):
    email: str
    tokens_after: int
    cost_usd: float
    saved_usd: float
    sessions: int
    detected_tools: list[str] = []
    mcp_registered: list[str] = []
    hook_registered: list[str] = []


class ToolSpend(BaseModel):
    ai_tool: str
    tokens_after: int
    cost_usd: float
    tokens_saved: int = 0
    cost_saved: float = 0.0


class ModelSpend(BaseModel):
    # provider is the vendor namespace (anthropic, openai, perplexity, ...);
    # model is the concrete vendor id (gpt-4o, claude-sonnet-4-5, ...). Both
    # are populated only for proxy-routed audit events — hook-only rows are
    # excluded from these aggregates by a `WHERE model IS NOT NULL` filter.
    provider: str
    model: str
    tokens_after: int
    cost_usd: float


class ProviderSpend(BaseModel):
    provider: str
    tokens_after: int
    cost_usd: float


class SpendSummary(BaseModel):
    workspace_id: str
    period: str
    active_developers: int
    events_today: int
    blocked_today: int
    tokens_saved_today: int
    total_tokens_before: int
    total_tokens_after: int
    total_saved_pct: int
    total_cost_usd: float
    total_saved_usd: float
    sessions: int = 0
    hook_sessions: int = 0
    by_developer: list[DeveloperSpend]
    by_ai_tool: list[ToolSpend]
    by_model: list[ModelSpend] = []
    by_provider: list[ProviderSpend] = []


class SessionOut(BaseModel):
    id: str
    workspace_id: str
    clerk_user_id: str | None
    user_email: str | None
    ai_tool: str
    started_at: str | None
    ended_at: str | None
    total_tokens_before: int
    total_tokens_after: int
    total_cost_usd: float
    total_saved_usd: float
    event_count: int
    violations_count: int
    client_ip: str | None = None
    os_info: str | None = None
    hostname: str | None = None
    intent: str | None = None
    session_parse_status: str | None = None


class BudgetCreate(BaseModel):
    workspace_id: str
    clerk_user_id: str | None = None    # null = workspace-wide
    email: str | None = None            # per-developer: frontend sends email, backend resolves to clerk_user_id
    agent_identity_id: str | None = None  # null = across all agents; non-null = per-agent budget (Added 0140)
    ai_tool: str | None = None          # null = across all tools; non-null = per-tool budget
    hard_cap_enabled: bool | None = None  # per-budget flag; the workspace-default row acts as a master switch, non-default rows opt-in individually
    monthly_limit_usd: float
    alert_threshold_pct: int = 80
    hard_limit_usd: float | None = None
    default_per_developer_usd: float | None = None  # workspace-wide record only


class BudgetOut(BaseModel):
    id: str
    workspace_id: str
    clerk_user_id: str | None
    email: str | None = None
    agent_identity_id: str | None = None  # Added 0140
    ai_tool: str | None = None
    hard_cap_enabled: bool = False
    monthly_limit_usd: float
    alert_threshold_pct: int
    hard_limit_usd: float | None
    default_per_developer_usd: float | None
    current_month_cost_usd: float
    created_at: str
    updated_at: str


# ── GET /guard/spend ──────────────────────────────────────────────────────────

import structlog as _structlog
_log = _structlog.get_logger(__name__)


@router.get("", response_model=SpendSummary)
def get_spend_summary(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    month: str | None = Query(default=None, description="Period in YYYY-MM format; defaults to current month"),
):
    """Spend summary for a workspace for the given month (defaults to current calendar month)."""
    try:
        return _get_spend_summary_inner(db, workspace_id, month)
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


# ── GET /guard/spend/sessions ─────────────────────────────────────────────────

@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    workspace_id: str = Depends(get_workspace_id),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """List sessions with cumulative spend totals."""
    org_ws = _org_ws_subquery(db, workspace_id)
    rows = (
        db.query(GuardSession)
        .filter(GuardSession.workspace_id.in_(org_ws))
        .order_by(GuardSession.started_at.desc())
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


# ── POST /guard/spend/budgets ─────────────────────────────────────────────────

@router.post("/budgets", response_model=BudgetOut, status_code=201)
def upsert_budget(
    body: BudgetCreate,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Create or update a spend budget for a user or the whole workspace."""
    try:
        ws_uuid = uuid.UUID(body.workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")

    clerk_user_id = body.clerk_user_id  # None = workspace-wide
    if clerk_user_id is None and body.email:
        session = (
            db.query(GuardSession)
            .filter(
                GuardSession.workspace_id == ws_uuid,
                GuardSession.user_email == body.email,
                GuardSession.clerk_user_id.isnot(None),
            )
            .order_by(GuardSession.started_at.desc())
            .first()
        )
        if session:
            clerk_user_id = session.clerk_user_id

    ai_tool = body.ai_tool or None  # normalize empty string
    agent_identity_id = body.agent_identity_id or None  # normalize empty string
    is_workspace_default = clerk_user_id is None and ai_tool is None and agent_identity_id is None

    # SQLAlchemy converts `column == None` to `IS NULL` — safe for all branches.
    existing = (
        db.query(GuardSpendBudget)
        .filter(
            GuardSpendBudget.workspace_id == ws_uuid,
            GuardSpendBudget.clerk_user_id == clerk_user_id,
            GuardSpendBudget.agent_identity_id == agent_identity_id,
            GuardSpendBudget.ai_tool == ai_tool,
        )
        .first()
    )
    now = _now()

    if existing:
        old = (existing.monthly_limit_usd, existing.hard_limit_usd)
        existing.monthly_limit_usd = body.monthly_limit_usd
        existing.alert_threshold_pct = body.alert_threshold_pct
        existing.hard_limit_usd = body.hard_limit_usd
        if body.default_per_developer_usd is not None or is_workspace_default:
            existing.default_per_developer_usd = body.default_per_developer_usd
        # Fix 2 (P1 #2): per-budget hard_cap_enabled. The workspace-default
        # row still functions as the master switch (checked by the ledger
        # before enforcing any row), but non-default rows can opt into
        # enforcement individually so per-tool and per-agent caps actually
        # participate in reservation. Pre-fix, only the default row could
        # be True and reserve_all silently skipped every other row.
        if body.hard_cap_enabled is not None:
            existing.hard_cap_enabled = bool(body.hard_cap_enabled)
        existing.updated_at = now
        db.commit()
        db.refresh(existing)
        budget = existing
        audit_action = "budget_updated"
        audit_summary = f"monthly {old[0]}→{body.monthly_limit_usd} hard {old[1]}→{body.hard_limit_usd}"
    else:
        budget = GuardSpendBudget(
            workspace_id=ws_uuid,
            clerk_user_id=clerk_user_id,
            agent_identity_id=agent_identity_id,
            ai_tool=ai_tool,
            monthly_limit_usd=body.monthly_limit_usd,
            alert_threshold_pct=body.alert_threshold_pct,
            hard_limit_usd=body.hard_limit_usd,
            default_per_developer_usd=body.default_per_developer_usd,
            hard_cap_enabled=bool(body.hard_cap_enabled) if body.hard_cap_enabled is not None else False,
        )
        db.add(budget)
        db.commit()
        db.refresh(budget)
        audit_action = "budget_created"
        audit_summary = f"monthly={body.monthly_limit_usd} hard={body.hard_limit_usd}"

    _audit_budget_change(db, ws_uuid, clerk_user_id, audit_action, audit_summary)

    current_cost = _current_month_cost(
        db, ws_uuid, clerk_user_id, ai_tool, agent_identity_id=agent_identity_id,
    )
    return _budget_out(budget, current_cost)


def _audit_budget_change(
    db: Session,
    workspace_id: uuid.UUID,
    clerk_user_id: str | None,
    action: str,
    summary: str,
) -> None:
    """Write a non-fatal audit row for budget mutations.

    target rule_id encodes 'workspace' or the clerk_user_id so the activity
    feed can show who the change applied to.
    """
    from app.modules.guard.models import GuardAuditEvent, chain_hash_for_insert
    try:
        ts = _now()
        prev_h, entry_h = chain_hash_for_insert(db, workspace_id, ts, action, "allowed")
        db.add(GuardAuditEvent(
            workspace_id=workspace_id,
            clerk_user_id=None,
            ai_tool="platform",
            tool_call=action,
            decision="allowed",
            rule_id=clerk_user_id or "workspace",
            input_summary=summary[:500],
            ts=ts,
            previous_hash=prev_h,
            entry_hash=entry_h,
        ))
        db.commit()
    except Exception:
        db.rollback()


# ── GET /guard/spend/budgets ──────────────────────────────────────────────────

@router.get("/budgets", response_model=list[BudgetOut])
def list_budgets(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """List all budgets for a workspace, each annotated with current month usage."""
    ws_uuid = uuid.UUID(workspace_id)
    org_ws = _org_ws_subquery(db, workspace_id)
    budgets = (
        db.query(GuardSpendBudget)
        .filter(GuardSpendBudget.workspace_id.in_(org_ws))
        .order_by(GuardSpendBudget.created_at.asc())
        .all()
    )
    uid_email: dict[str, str] = {
        r.clerk_user_id: r.user_email
        for r in db.query(GuardSession.clerk_user_id, GuardSession.user_email)
        .filter(
            GuardSession.workspace_id.in_(org_ws),
            GuardSession.clerk_user_id.isnot(None),
            GuardSession.user_email.isnot(None),
        )
        .distinct()
        .all()
        if r.clerk_user_id
    }
    return [
        _budget_out(
            b,
            _current_month_cost(
                db, ws_uuid, b.clerk_user_id, b.ai_tool,
                agent_identity_id=b.agent_identity_id,
            ),
            uid_email.get(b.clerk_user_id) if b.clerk_user_id else None,
        )
        for b in budgets
    ]


# ── DELETE /guard/spend/budgets/{budget_id} ──────────────────────────────────

@router.delete("/budgets/{budget_id}", status_code=204)
def delete_budget(
    budget_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Delete a spend budget row. Used to remove per-tool caps.

    The workspace-default row (clerk_user_id NULL, ai_tool NULL) cannot be
    deleted through this endpoint — it carries the hard_cap_enabled flag
    and clearing it via DELETE would silently drop enforcement config.
    """
    try:
        row_uuid = uuid.UUID(budget_id)
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid id")
    budget = (
        db.query(GuardSpendBudget)
        .filter(GuardSpendBudget.id == row_uuid, GuardSpendBudget.workspace_id == ws_uuid)
        .first()
    )
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    # Fix 6c (P2): agent-scoped rows are NOT the workspace default even
    # when clerk_user_id and ai_tool are both NULL. Only the true default
    # row (all three scope keys NULL) carries the master enforcement flag.
    if (
        budget.clerk_user_id is None
        and budget.ai_tool is None
        and budget.agent_identity_id is None
    ):
        raise HTTPException(
            status_code=400,
            detail="Workspace-default budget cannot be deleted — edit its values instead.",
        )
    label = (
        budget.ai_tool
        or budget.clerk_user_id
        or (f"agent:{budget.agent_identity_id}" if budget.agent_identity_id else "workspace")
    )
    db.delete(budget)
    db.commit()
    _audit_budget_change(db, ws_uuid, budget.clerk_user_id, "budget_deleted", f"deleted {label}")
    return None


# ── Private helpers ───────────────────────────────────────────────────────────

def _current_month_cost(
    db: Session,
    ws_uuid: uuid.UUID,
    clerk_user_id: str | None,
    ai_tool: str | None = None,
    agent_identity_id: str | None = None,
) -> float:
    """Sum cost_usd_after for the current calendar month, scoped to workspace
    (and optionally to a specific clerk_user_id, agent_identity_id, and/or
    ai_tool).

    Fix 6a (P2): agent_identity_id was previously ignored so a per-agent
    budget's 'current cost' row in the list endpoint returned the workspace
    total instead of the agent's share.
    """
    period_start = _current_period_start()
    q = db.query(
        func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0)
    ).filter(
        GuardAuditEvent.workspace_id == ws_uuid,
        GuardAuditEvent.ts >= period_start,
    )
    if clerk_user_id is not None:
        q = q.filter(GuardAuditEvent.clerk_user_id == clerk_user_id)
    if ai_tool is not None:
        q = q.filter(GuardAuditEvent.ai_tool == ai_tool)
    if agent_identity_id is not None:
        q = q.filter(GuardAuditEvent.agent_identity_id == agent_identity_id)
    return float(q.scalar() or 0.0)


# ── GET /guard/spend/budget-check ─────────────────────────────────────────────

class BudgetCheckOut(BaseModel):
    hard_blocked: bool
    reason: str | None = None
    monthly_cost_usd: float
    hard_limit_usd: float | None


@router.get("/budget-check", response_model=BudgetCheckOut)
def budget_check(
    workspace_id: str = Query(...),
    clerk_user_id: str | None = Query(default=None),
    ai_tool: str | None = Query(default=None),
    transport: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Hard-cap check called by the guard hook before each tool use.

    Enforcement is gated by a single workspace-global flag on the default row
    (clerk_user_id NULL, ai_tool NULL). When the flag is off, this endpoint
    always returns hard_blocked=False regardless of any configured limits.

    When ai_tool is provided AND a per-tool row exists for that tool, that
    row's caps are checked with cost sums scoped to the same tool — so a
    Codex Desktop overspend can't block a Claude Code caller.

    Fix 4 (P1 #4): transport is a separate cap dimension. Admins can set
    ``ai_tool='gateway'`` or ``'mcp'`` to cap the aggregate transport
    pool regardless of which client tool called it. When a request comes
    through the gateway, the caller passes ``transport='gateway'`` and
    this check aggregates events with ``source='gateway'`` against the
    matching budget row's cap.
    """
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return BudgetCheckOut(hard_blocked=False, monthly_cost_usd=0.0, hard_limit_usd=None)

    # Guard installed check — prevents enumeration of arbitrary workspace IDs
    if not db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first():
        return BudgetCheckOut(hard_blocked=False, monthly_cost_usd=0.0, hard_limit_usd=None)

    # Fix 3 (P1 #3): filter agent_identity_id IS NULL so an agent-scoped
    # row (added by migration 0140) does NOT masquerade as the workspace
    # default. Legacy budget_check() only handles workspace + per-user
    # scope; agent scope is handled by lookup_applicable_budgets().
    workspace_budget = (
        db.query(GuardSpendBudget)
        .filter(
            GuardSpendBudget.workspace_id == ws_uuid,
            GuardSpendBudget.clerk_user_id.is_(None),
            GuardSpendBudget.agent_identity_id.is_(None),
            GuardSpendBudget.ai_tool.is_(None),
        )
        .first()
    )

    # R12 fix (reviewer P1): per-budget hard_cap_enabled semantics.
    # Pre-fix, this was a workspace-wide kill switch: if the workspace-
    # default row's flag was off, NO cap fired even for scoped rows
    # with their own enforcement on. That contradicted reserve_all
    # (post Fix 2 #2102), which respects each row's own flag.
    #
    # New rule (consistent with reserve_all): each budget row's own
    # hard_cap_enabled is authoritative for THAT row's cap. Admins
    # who want a kill switch flip every row (or file a follow-up for
    # a workspace-level enforcement flag distinct from the workspace-
    # default budget row).
    if workspace_budget is None:
        return BudgetCheckOut(
            hard_blocked=False,
            monthly_cost_usd=0.0,
            hard_limit_usd=None,
        )

    period_start = _current_period_start()

    def _sum_cost(
        *,
        scoped_clerk: str | None = None,
        scoped_tool: str | None = None,
        scoped_source: str | None = None,
    ) -> float:
        q = db.query(func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0)).filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= period_start,
        )
        if scoped_clerk is not None:
            q = q.filter(GuardAuditEvent.clerk_user_id == scoped_clerk)
        if scoped_tool is not None:
            q = q.filter(GuardAuditEvent.ai_tool == scoped_tool)
        if scoped_source is not None:
            q = q.filter(GuardAuditEvent.source == scoped_source)
        return float(q.scalar() or 0.0)

    tool_budget = None
    if ai_tool:
        tool_budget = (
            db.query(GuardSpendBudget)
            .filter(
                GuardSpendBudget.workspace_id == ws_uuid,
                GuardSpendBudget.clerk_user_id.is_(None),
                GuardSpendBudget.agent_identity_id.is_(None),  # Fix 3 (P1 #3)
                GuardSpendBudget.ai_tool == ai_tool,
            )
            .first()
        )

    # 1a. Team-scoped per-tool cap (F3 — cross-tool bleed fix).
    # R12: gate on this row's own hard_cap_enabled.
    if (
        tool_budget
        and tool_budget.hard_limit_usd is not None
        and tool_budget.hard_cap_enabled
    ):
        tool_cost = _sum_cost(scoped_tool=ai_tool)
        if tool_cost >= tool_budget.hard_limit_usd:
            return BudgetCheckOut(
                hard_blocked=True,
                reason=(
                    f"Your team's monthly {ai_tool} budget of ${tool_budget.hard_limit_usd:.2f} "
                    f"has been reached. New {ai_tool} calls are paused. Contact your security team."
                ),
                monthly_cost_usd=tool_cost,
                hard_limit_usd=tool_budget.hard_limit_usd,
            )

    # 1a-bis. Fix 4 (P1 #4): transport-scoped cap (workspace pool per
    # surface). An admin who sets ai_tool='gateway' expects every gateway
    # request to consume the same pool regardless of client tool label.
    # This check fires when the caller passes transport='gateway' (or
    # 'mcp'), matches a budget row keyed on that transport value, and
    # aggregates events with the matching source column.
    if transport:
        transport_budget = (
            db.query(GuardSpendBudget)
            .filter(
                GuardSpendBudget.workspace_id == ws_uuid,
                GuardSpendBudget.clerk_user_id.is_(None),
                GuardSpendBudget.agent_identity_id.is_(None),
                GuardSpendBudget.ai_tool == transport,
            )
            .first()
        )
        if (
            transport_budget
            and transport_budget.hard_limit_usd is not None
            and transport_budget.hard_cap_enabled  # R12
        ):
            transport_cost = _sum_cost(scoped_source=transport)
            if transport_cost >= transport_budget.hard_limit_usd:
                return BudgetCheckOut(
                    hard_blocked=True,
                    reason=(
                        f"Your team's monthly {transport} pool budget of "
                        f"${transport_budget.hard_limit_usd:.2f} has been reached. "
                        f"New {transport} traffic is paused. Contact your security team."
                    ),
                    monthly_cost_usd=transport_cost,
                    hard_limit_usd=transport_budget.hard_limit_usd,
                )

    # 1b. Team-scoped across-all-tools cap (unchanged behavior).
    # R12: gate on the workspace-default row's own hard_cap_enabled.
    workspace_cost = _sum_cost()
    if (
        workspace_budget.hard_limit_usd is not None
        and workspace_budget.hard_cap_enabled
    ):
        if workspace_cost >= workspace_budget.hard_limit_usd:
            return BudgetCheckOut(
                hard_blocked=True,
                reason=(
                    f"Your team's monthly AI budget of ${workspace_budget.hard_limit_usd:.2f} has been reached. "
                    f"New tool calls are paused until the limit is raised. Contact your security team."
                ),
                monthly_cost_usd=workspace_cost,
                hard_limit_usd=workspace_budget.hard_limit_usd,
            )

    # 2. Per-user cap (fires only when clerk_user_id is supplied).
    if clerk_user_id:
        user_tool_budget = None
        if ai_tool:
            user_tool_budget = (
                db.query(GuardSpendBudget)
                .filter(
                    GuardSpendBudget.workspace_id == ws_uuid,
                    GuardSpendBudget.clerk_user_id == clerk_user_id,
                    GuardSpendBudget.agent_identity_id.is_(None),  # Fix 3 (P1 #3)
                    GuardSpendBudget.ai_tool == ai_tool,
                )
                .first()
            )
            # R12 fix: the enforcement lines below check user_tool_budget.hard_cap_enabled.
        user_budget = (
            db.query(GuardSpendBudget)
            .filter(
                GuardSpendBudget.workspace_id == ws_uuid,
                GuardSpendBudget.clerk_user_id == clerk_user_id,
                GuardSpendBudget.agent_identity_id.is_(None),  # Fix 3 (P1 #3)
                GuardSpendBudget.ai_tool.is_(None),
            )
            .first()
        )

        # Priority: most specific per-user limit wins; workspace defaults are fallbacks.
        hard_limit: float | None = None
        scoped_tool: str | None = None
        if user_tool_budget and user_tool_budget.hard_limit_usd is not None:
            hard_limit = user_tool_budget.hard_limit_usd
            scoped_tool = ai_tool
        elif user_budget and user_budget.hard_limit_usd is not None:
            hard_limit = user_budget.hard_limit_usd
        elif tool_budget and tool_budget.default_per_developer_usd is not None:
            hard_limit = tool_budget.default_per_developer_usd
            scoped_tool = ai_tool
        elif workspace_budget.default_per_developer_usd is not None:
            hard_limit = workspace_budget.default_per_developer_usd

        if hard_limit is not None:
            user_cost = _sum_cost(scoped_clerk=clerk_user_id, scoped_tool=scoped_tool)
            if user_cost >= hard_limit:
                tool_hint = f" for {ai_tool}" if scoped_tool else ""
                return BudgetCheckOut(
                    hard_blocked=True,
                    reason=(
                        f"You've reached your monthly AI spend limit of ${hard_limit:.2f}{tool_hint}. "
                        f"New tool calls are paused. Contact your manager to have your limit raised."
                    ),
                    monthly_cost_usd=user_cost,
                    hard_limit_usd=hard_limit,
                )

    return BudgetCheckOut(
        hard_blocked=False,
        monthly_cost_usd=workspace_cost,
        hard_limit_usd=workspace_budget.hard_limit_usd,
    )


def _budget_out(budget: GuardSpendBudget, current_cost: float, email: str | None = None) -> BudgetOut:
    return BudgetOut(
        id=str(budget.id),
        workspace_id=str(budget.workspace_id),
        clerk_user_id=budget.clerk_user_id,
        email=email,
        agent_identity_id=budget.agent_identity_id,
        ai_tool=budget.ai_tool,
        hard_cap_enabled=bool(budget.hard_cap_enabled),
        monthly_limit_usd=budget.monthly_limit_usd,
        alert_threshold_pct=budget.alert_threshold_pct,
        hard_limit_usd=budget.hard_limit_usd,
        default_per_developer_usd=budget.default_per_developer_usd,
        current_month_cost_usd=round(current_cost, 6),
        created_at=budget.created_at.isoformat(),
        updated_at=budget.updated_at.isoformat(),
    )


# ── GET /guard/spend/reservations ─────────────────────────────────────────────
#
# PR-B: per-scope reservation state for a single request. The gateway wire-in
# (PR-A2b) writes one budget_reservations row per applicable budget scope, all
# tagged with the audit request_id. The drawer UI calls this endpoint with a
# blocked-request's request_id and renders one row per reservation showing
# scope + reserved amount + status (open / released / committed).
#
# Cardinality-safe by design: only rows for the caller's workspace are ever
# returned; request_id is a UUID so enumeration is impractical.


class ReservationScopeOut(BaseModel):
    """Per-scope reservation record for the drawer."""
    reservation_id: str
    workspace_id: str
    clerk_user_id: str | None
    agent_identity_id: str | None
    ai_tool: str | None
    source: str | None
    client_tool: str | None
    period_key: str
    estimated_cents: int
    actual_cents: int | None
    status: str  # 'open' | 'released' | 'committed'
    created_at: str
    resolved_at: str | None


@router.get("/reservations", response_model=list[ReservationScopeOut])
def list_reservations_for_request(
    request_id: str = Query(..., description="Audit event request_id (UUID)"),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Return all reservation rows correlated to a single audit request.

    A gateway request that reaches the ledger writes one BudgetReservation
    row per applicable hard-cap budget, each tagged with the same
    ``request_id`` as the audit event. The drawer UI calls this endpoint
    to render per-scope reserved/settled/released rows against the block.
    """
    try:
        ws_uuid = uuid.UUID(workspace_id)
        req_uuid = uuid.UUID(request_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id or request_id")

    rows = (
        db.query(BudgetReservation)
        .filter(
            BudgetReservation.workspace_id == ws_uuid,
            BudgetReservation.request_id == req_uuid,
        )
        .order_by(BudgetReservation.created_at.asc())
        .all()
    )
    return [
        ReservationScopeOut(
            reservation_id=str(r.id),
            workspace_id=str(r.workspace_id),
            clerk_user_id=r.clerk_user_id,
            agent_identity_id=r.agent_identity_id,
            ai_tool=r.ai_tool,
            source=r.source,
            client_tool=r.client_tool,
            period_key=r.period_key,
            estimated_cents=int(r.estimated_cents),
            actual_cents=int(r.actual_cents) if r.actual_cents is not None else None,
            status=r.status,
            created_at=r.created_at.isoformat(),
            resolved_at=r.resolved_at.isoformat() if r.resolved_at else None,
        )
        for r in rows
    ]
