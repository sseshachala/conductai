"""
GET  /guard/spend                  — spend summary for team (current calendar month)
GET  /guard/spend/sessions         — list sessions with totals
POST /guard/spend/budgets          — create or update a budget for member or team-wide
GET  /guard/spend/budgets          — list all budgets with current month usage
GET  /guard/spend/budget-check     — hard-cap check called by the guard hook (no Clerk auth)
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_guard_org_id
from app.core.database import get_db
from app.modules.guard.models import GuardAuditEvent, GuardSession, GuardSpendBudget, GuardTeam, GuardMember

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
    team_id: str
    period: str
    total_tokens_before: int
    total_tokens_after: int
    total_saved_pct: int
    total_cost_usd: float
    total_saved_usd: float
    by_developer: list[DeveloperSpend]
    by_ai_tool: list[ToolSpend]


class SessionOut(BaseModel):
    id: str
    team_id: str
    member_id: str | None
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
    team_id: str
    member_id: str | None = None   # null = team-wide
    email: str | None = None       # alternative to member_id for per-dev budgets
    monthly_limit_usd: float
    alert_threshold_pct: int = 80
    hard_limit_usd: float | None = None
    default_per_developer_usd: float | None = None  # team-wide record only


class BudgetOut(BaseModel):
    id: str
    team_id: str
    member_id: str | None
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
    team_id: str = Query(..., description="Team ID"),
    month: str | None = Query(default=None, description="Period in YYYY-MM format; defaults to current month"),
    db: Session = Depends(get_db),
    _org_id: str = Depends(get_guard_org_id),
):
    """Spend summary for a team for the given month (defaults to current calendar month)."""
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
            GuardAuditEvent.team_id == team_id,
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
            GuardAuditEvent.team_id == team_id,
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
            GuardSession.team_id == team_id,
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
            GuardAuditEvent.team_id == team_id,
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

    return SpendSummary(
        team_id=team_id,
        period=month or _period_label(),
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
    team_id: str = Query(..., description="Team ID"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    _org_id: str = Depends(get_guard_org_id),
):
    """List sessions with cumulative spend totals."""
    rows = (
        db.query(GuardSession)
        .filter(GuardSession.team_id == team_id)
        .order_by(GuardSession.started_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [
        SessionOut(
            id=str(s.id),
            team_id=str(s.team_id),
            member_id=str(s.member_id) if s.member_id else None,
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
    _org_id: str = Depends(get_guard_org_id),
):
    """Create or update a spend budget for a member or the whole team."""
    import uuid as _uuid
    from fastapi import HTTPException as _HTTPException

    # Resolve email → member_id if provided
    resolved_member_id = body.member_id
    if resolved_member_id is None and body.email:
        member = db.query(GuardMember).filter(GuardMember.email == body.email).first()
        if not member:
            raise _HTTPException(status_code=404, detail=f"Member with email {body.email!r} not found")
        resolved_member_id = str(member.id)

    # Upsert: one budget per (team_id, member_id) pair
    try:
        team_uuid = _uuid.UUID(body.team_id)
        member_uuid = _uuid.UUID(resolved_member_id) if resolved_member_id else None
    except ValueError:
        raise _HTTPException(status_code=422, detail="Invalid team_id or member_id")

    existing = (
        db.query(GuardSpendBudget)
        .filter(
            GuardSpendBudget.team_id == team_uuid,
            GuardSpendBudget.member_id == member_uuid,
        )
        .first()
    )
    now = _now()

    if existing:
        existing.monthly_limit_usd = body.monthly_limit_usd
        existing.alert_threshold_pct = body.alert_threshold_pct
        existing.hard_limit_usd = body.hard_limit_usd
        if body.default_per_developer_usd is not None or member_uuid is None:
            existing.default_per_developer_usd = body.default_per_developer_usd
        existing.updated_at = now
        db.commit()
        db.refresh(existing)
        budget = existing
    else:
        budget = GuardSpendBudget(
            team_id=team_uuid,
            member_id=member_uuid,
            monthly_limit_usd=body.monthly_limit_usd,
            alert_threshold_pct=body.alert_threshold_pct,
            hard_limit_usd=body.hard_limit_usd,
            default_per_developer_usd=body.default_per_developer_usd,
        )
        db.add(budget)
        db.commit()
        db.refresh(budget)

    current_cost = _current_month_cost(db, body.team_id, resolved_member_id)
    return _budget_out(budget, current_cost)


# ── GET /guard/spend/budgets ──────────────────────────────────────────────────

@router.get("/budgets", response_model=list[BudgetOut])
def list_budgets(
    team_id: str = Query(..., description="Team ID"),
    db: Session = Depends(get_db),
    _org_id: str = Depends(get_guard_org_id),
):
    """List all budgets for a team, each annotated with current month usage."""
    budgets = (
        db.query(GuardSpendBudget)
        .filter(GuardSpendBudget.team_id == team_id)
        .order_by(GuardSpendBudget.created_at.asc())
        .all()
    )
    return [
        _budget_out(b, _current_month_cost(db, team_id, b.member_id))
        for b in budgets
    ]


# ── Private helpers ───────────────────────────────────────────────────────────

def _current_month_cost(db: Session, team_id: str, member_id: str | None) -> float:
    """Sum cost_usd_after for the current calendar month, scoped to team (and
    optionally a specific member via their email lookup)."""
    period_start = _current_period_start()
    q = db.query(
        func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0)
    ).filter(
        GuardAuditEvent.team_id == team_id,
        GuardAuditEvent.ts >= period_start,
    )

    if member_id is not None:
        # Resolve member_id -> email for the join
        member = db.query(GuardMember).filter(GuardMember.id == member_id).first()
        if member:
            q = q.filter(GuardAuditEvent.user_email == member.email)

    return float(q.scalar() or 0.0)


# ── GET /guard/spend/budget-check ─────────────────────────────────────────────

class BudgetCheckOut(BaseModel):
    hard_blocked: bool
    reason: str | None = None
    monthly_cost_usd: float
    hard_limit_usd: float | None


@router.get("/budget-check", response_model=BudgetCheckOut)
def budget_check(
    team_id: str = Query(...),
    email: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    """Hard-cap check called by the guard hook before each tool use. No Clerk auth —
    team_id must exist in guard_teams (same trust model as POST /guard/events)."""
    import uuid as _uuid

    try:
        team_uuid = _uuid.UUID(team_id)
    except ValueError:
        return BudgetCheckOut(hard_blocked=False, monthly_cost_usd=0.0, hard_limit_usd=None)

    period_start = _current_period_start()

    team_budget = (
        db.query(GuardSpendBudget)
        .filter(GuardSpendBudget.team_id == team_uuid, GuardSpendBudget.member_id.is_(None))
        .first()
    )

    team_cost = float(
        db.query(func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0))
        .filter(GuardAuditEvent.team_id == team_uuid, GuardAuditEvent.ts >= period_start)
        .scalar() or 0.0
    )

    # Check team-wide hard cap
    if team_budget and team_budget.hard_limit_usd is not None:
        if team_cost >= team_budget.hard_limit_usd:
            return BudgetCheckOut(
                hard_blocked=True,
                reason=(
                    f"Team monthly spend ${team_cost:.2f} has reached the hard cap "
                    f"of ${team_budget.hard_limit_usd:.2f}. Contact your security team."
                ),
                monthly_cost_usd=team_cost,
                hard_limit_usd=team_budget.hard_limit_usd,
            )

    # Check per-member hard cap if email provided
    if email:
        member = (
            db.query(GuardMember)
            .filter(GuardMember.team_id == team_uuid, GuardMember.email == email)
            .first()
        )
        if member:
            member_budget = (
                db.query(GuardSpendBudget)
                .filter(
                    GuardSpendBudget.team_id == team_uuid,
                    GuardSpendBudget.member_id == member.id,
                )
                .first()
            )
            # Fall back to team default_per_developer_usd if no per-member budget
            hard_limit = None
            if member_budget and member_budget.hard_limit_usd is not None:
                hard_limit = member_budget.hard_limit_usd
            elif team_budget and team_budget.default_per_developer_usd is not None:
                hard_limit = team_budget.default_per_developer_usd

            if hard_limit is not None:
                member_cost = float(
                    db.query(func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0))
                    .filter(
                        GuardAuditEvent.team_id == team_uuid,
                        GuardAuditEvent.user_email == email,
                        GuardAuditEvent.ts >= period_start,
                    )
                    .scalar() or 0.0
                )
                if member_cost >= hard_limit:
                    return BudgetCheckOut(
                        hard_blocked=True,
                        reason=(
                            f"Your monthly spend ${member_cost:.2f} has reached your "
                            f"hard cap of ${hard_limit:.2f}. Contact your manager."
                        ),
                        monthly_cost_usd=member_cost,
                        hard_limit_usd=hard_limit,
                    )

    return BudgetCheckOut(
        hard_blocked=False,
        monthly_cost_usd=team_cost,
        hard_limit_usd=team_budget.hard_limit_usd if team_budget else None,
    )


def _budget_out(budget: GuardSpendBudget, current_cost: float) -> BudgetOut:
    return BudgetOut(
        id=str(budget.id),
        team_id=str(budget.team_id),
        member_id=str(budget.member_id) if budget.member_id else None,
        monthly_limit_usd=budget.monthly_limit_usd,
        alert_threshold_pct=budget.alert_threshold_pct,
        hard_limit_usd=budget.hard_limit_usd,
        default_per_developer_usd=budget.default_per_developer_usd,
        current_month_cost_usd=round(current_cost, 6),
        created_at=budget.created_at.isoformat(),
        updated_at=budget.updated_at.isoformat(),
    )
