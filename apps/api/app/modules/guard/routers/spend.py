"""
GET  /guard/spend                  — spend summary for workspace (current calendar month)
GET  /guard/spend/sessions         — list sessions with totals
POST /guard/spend/budgets          — create or update a budget for user or workspace-wide
GET  /guard/spend/budgets          — list all budgets with current month usage
GET  /guard/spend/budget-check     — hard-cap check called by the guard hook (no Clerk auth)
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, distinct, or_, text
from sqlalchemy.orm import Session

from fastapi import HTTPException
from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.modules.guard.models import GuardAuditEvent, GuardConfig, GuardSession, GuardSpendBudget

router = APIRouter(prefix="/guard/spend", tags=["guard"])


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


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class DeveloperSpend(BaseModel):
    email: str
    tokens_after: int
    cost_usd: float
    saved_usd: float
    sessions: int


class ToolSpend(BaseModel):
    ai_tool: str
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
    by_developer: list[DeveloperSpend]
    by_ai_tool: list[ToolSpend]


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


class BudgetCreate(BaseModel):
    workspace_id: str
    clerk_user_id: str | None = None    # null = workspace-wide
    monthly_limit_usd: float
    alert_threshold_pct: int = 80
    hard_limit_usd: float | None = None
    default_per_developer_usd: float | None = None  # workspace-wide record only


class BudgetOut(BaseModel):
    id: str
    workspace_id: str
    clerk_user_id: str | None
    monthly_limit_usd: float
    alert_threshold_pct: int
    hard_limit_usd: float | None
    default_per_developer_usd: float | None
    current_month_cost_usd: float
    created_at: str
    updated_at: str


# ── GET /guard/spend ──────────────────────────────────────────────────────────

@router.get("", response_model=SpendSummary)
def get_spend_summary(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    month: str | None = Query(default=None, description="Period in YYYY-MM format; defaults to current month"),
):
    """Spend summary for a workspace for the given month (defaults to current calendar month)."""
    ws_uuid = uuid.UUID(workspace_id)
    period_start = _parse_period_start(month)

    # Aggregate totals
    totals = (
        db.query(
            func.coalesce(func.sum(GuardAuditEvent.tokens_before), 0).label("tokens_before"),
            func.coalesce(func.sum(GuardAuditEvent.tokens_after), 0).label("tokens_after"),
            func.coalesce(func.sum(GuardAuditEvent.cost_usd_before), 0.0).label("cost_before"),
            func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0).label("cost_after"),
        )
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= period_start,
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
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= period_start,
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
            GuardSession.workspace_id == ws_uuid,
            GuardSession.started_at >= period_start,
            GuardSession.user_email.isnot(None),
        )
        .group_by(GuardSession.user_email)
        .all()
    )
    for email, cnt in session_rows:
        if email:
            session_counts[email] = cnt

    by_developer = [
        DeveloperSpend(
            email=row.user_email,
            tokens_after=int(row.tokens_after),
            cost_usd=round(float(row.cost_usd), 6),
            saved_usd=round(float(row.saved_usd), 6),
            sessions=session_counts.get(row.user_email, 0),
        )
        for row in dev_rows
    ]

    # By AI tool
    tool_rows = (
        db.query(
            GuardAuditEvent.ai_tool,
            func.coalesce(func.sum(GuardAuditEvent.tokens_after), 0).label("tokens_after"),
            func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0).label("cost_usd"),
        )
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= period_start,
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
        )
        for row in tool_rows
    ]

    # Today stats — for the dashboard stat cards
    from datetime import date
    today_start = datetime.combine(date.today(), datetime.min.time()).replace(tzinfo=timezone.utc)
    events_today = int(
        db.query(func.count(GuardAuditEvent.id))
        .filter(GuardAuditEvent.workspace_id == ws_uuid, GuardAuditEvent.ts >= today_start)
        .scalar() or 0
    )
    blocked_today = int(
        db.query(func.count(GuardAuditEvent.id))
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= today_start,
            GuardAuditEvent.decision == "blocked",
        )
        .scalar() or 0
    )
    tokens_saved_today = int(
        db.query(func.coalesce(
            func.sum(GuardAuditEvent.tokens_before - GuardAuditEvent.tokens_after), 0
        ))
        .filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= today_start,
            GuardAuditEvent.tokens_before.isnot(None),
            GuardAuditEvent.tokens_after.isnot(None),
        )
        .scalar() or 0
    )

    # Count distinct active devs via raw SQL (avoids SQLAlchemy DISTINCT-expression quirks)
    active_developers = int(db.execute(
        text("""
            SELECT COUNT(DISTINCT COALESCE(user_email, clerk_user_id))
            FROM guard_audit_events
            WHERE workspace_id = :ws
              AND ts >= :since
              AND (user_email IS NOT NULL OR clerk_user_id IS NOT NULL)
        """),
        {"ws": str(ws_uuid), "since": period_start},
    ).scalar() or 0)
    # Fallback: if all events are fully anonymous, show 1 whenever any events exist this period
    if active_developers == 0:
        has_events = int(db.execute(
            text("SELECT COUNT(*) FROM guard_audit_events WHERE workspace_id = :ws AND ts >= :since"),
            {"ws": str(ws_uuid), "since": period_start},
        ).scalar() or 0)
        if has_events > 0:
            active_developers = 1

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
        by_developer=by_developer,
        by_ai_tool=by_ai_tool,
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
    ws_uuid = uuid.UUID(workspace_id)
    rows = (
        db.query(GuardSession)
        .filter(GuardSession.workspace_id == ws_uuid)
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

    existing = (
        db.query(GuardSpendBudget)
        .filter(
            GuardSpendBudget.workspace_id == ws_uuid,
            GuardSpendBudget.clerk_user_id == clerk_user_id,
        )
        .first()
    )
    now = _now()

    if existing:
        existing.monthly_limit_usd = body.monthly_limit_usd
        existing.alert_threshold_pct = body.alert_threshold_pct
        existing.hard_limit_usd = body.hard_limit_usd
        if body.default_per_developer_usd is not None or clerk_user_id is None:
            existing.default_per_developer_usd = body.default_per_developer_usd
        existing.updated_at = now
        db.commit()
        db.refresh(existing)
        budget = existing
    else:
        budget = GuardSpendBudget(
            workspace_id=ws_uuid,
            clerk_user_id=clerk_user_id,
            monthly_limit_usd=body.monthly_limit_usd,
            alert_threshold_pct=body.alert_threshold_pct,
            hard_limit_usd=body.hard_limit_usd,
            default_per_developer_usd=body.default_per_developer_usd,
        )
        db.add(budget)
        db.commit()
        db.refresh(budget)

    current_cost = _current_month_cost(db, ws_uuid, clerk_user_id)
    return _budget_out(budget, current_cost)


# ── GET /guard/spend/budgets ──────────────────────────────────────────────────

@router.get("/budgets", response_model=list[BudgetOut])
def list_budgets(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """List all budgets for a workspace, each annotated with current month usage."""
    ws_uuid = uuid.UUID(workspace_id)
    budgets = (
        db.query(GuardSpendBudget)
        .filter(GuardSpendBudget.workspace_id == ws_uuid)
        .order_by(GuardSpendBudget.created_at.asc())
        .all()
    )
    return [
        _budget_out(b, _current_month_cost(db, ws_uuid, b.clerk_user_id))
        for b in budgets
    ]


# ── Private helpers ───────────────────────────────────────────────────────────

def _current_month_cost(db: Session, ws_uuid: uuid.UUID, clerk_user_id: str | None) -> float:
    """Sum cost_usd_after for the current calendar month, scoped to workspace
    (and optionally to a specific clerk_user_id)."""
    period_start = _current_period_start()
    q = db.query(
        func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0)
    ).filter(
        GuardAuditEvent.workspace_id == ws_uuid,
        GuardAuditEvent.ts >= period_start,
    )
    if clerk_user_id is not None:
        q = q.filter(GuardAuditEvent.clerk_user_id == clerk_user_id)
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
    db: Session = Depends(get_db),
):
    """Hard-cap check called by the guard hook before each tool use. No Clerk auth —
    workspace_id must exist in guard_config (same trust model as POST /guard/events)."""
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return BudgetCheckOut(hard_blocked=False, monthly_cost_usd=0.0, hard_limit_usd=None)

    # Guard installed check — prevents enumeration of arbitrary workspace IDs
    if not db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first():
        return BudgetCheckOut(hard_blocked=False, monthly_cost_usd=0.0, hard_limit_usd=None)

    period_start = _current_period_start()

    workspace_budget = (
        db.query(GuardSpendBudget)
        .filter(GuardSpendBudget.workspace_id == ws_uuid, GuardSpendBudget.clerk_user_id.is_(None))
        .first()
    )

    workspace_cost = float(
        db.query(func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0))
        .filter(GuardAuditEvent.workspace_id == ws_uuid, GuardAuditEvent.ts >= period_start)
        .scalar() or 0.0
    )

    # Check workspace-wide hard cap
    if workspace_budget and workspace_budget.hard_limit_usd is not None:
        if workspace_cost >= workspace_budget.hard_limit_usd:
            return BudgetCheckOut(
                hard_blocked=True,
                reason=(
                    f"Workspace monthly spend ${workspace_cost:.2f} has reached the hard cap "
                    f"of ${workspace_budget.hard_limit_usd:.2f}. Contact your security team."
                ),
                monthly_cost_usd=workspace_cost,
                hard_limit_usd=workspace_budget.hard_limit_usd,
            )

    # Check per-user hard cap if clerk_user_id provided
    if clerk_user_id:
        user_budget = (
            db.query(GuardSpendBudget)
            .filter(
                GuardSpendBudget.workspace_id == ws_uuid,
                GuardSpendBudget.clerk_user_id == clerk_user_id,
            )
            .first()
        )
        hard_limit = None
        if user_budget and user_budget.hard_limit_usd is not None:
            hard_limit = user_budget.hard_limit_usd
        elif workspace_budget and workspace_budget.default_per_developer_usd is not None:
            hard_limit = workspace_budget.default_per_developer_usd

        if hard_limit is not None:
            user_cost = float(
                db.query(func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0))
                .filter(
                    GuardAuditEvent.workspace_id == ws_uuid,
                    GuardAuditEvent.clerk_user_id == clerk_user_id,
                    GuardAuditEvent.ts >= period_start,
                )
                .scalar() or 0.0
            )
            if user_cost >= hard_limit:
                return BudgetCheckOut(
                    hard_blocked=True,
                    reason=(
                        f"Your monthly spend ${user_cost:.2f} has reached your "
                        f"hard cap of ${hard_limit:.2f}. Contact your manager."
                    ),
                    monthly_cost_usd=user_cost,
                    hard_limit_usd=hard_limit,
                )

    return BudgetCheckOut(
        hard_blocked=False,
        monthly_cost_usd=workspace_cost,
        hard_limit_usd=workspace_budget.hard_limit_usd if workspace_budget else None,
    )


def _budget_out(budget: GuardSpendBudget, current_cost: float) -> BudgetOut:
    return BudgetOut(
        id=str(budget.id),
        workspace_id=str(budget.workspace_id),
        clerk_user_id=budget.clerk_user_id,
        monthly_limit_usd=budget.monthly_limit_usd,
        alert_threshold_pct=budget.alert_threshold_pct,
        hard_limit_usd=budget.hard_limit_usd,
        default_per_developer_usd=budget.default_per_developer_usd,
        current_month_cost_usd=round(current_cost, 6),
        created_at=budget.created_at.isoformat(),
        updated_at=budget.updated_at.isoformat(),
    )
