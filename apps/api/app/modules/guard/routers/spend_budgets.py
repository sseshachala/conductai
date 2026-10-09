"""ConductGuard spend — budget CRUD endpoints (/guard/spend/budgets)."""

import uuid
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.modules.guard.models import GuardAuditEvent, GuardSession, GuardSpendBudget
from app.modules.guard.routers.spend_common import (
    BudgetCreate,
    BudgetOut,
    _current_period_start,
    _now,
    _org_ws_subquery,
)

router = APIRouter(prefix="/guard/spend", tags=["guard"])


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
    groups = _month_cost_groups(db, ws_uuid) if budgets else []
    return [
        _budget_out(
            b,
            _cost_from_groups(groups, b),
            uid_email.get(b.clerk_user_id) if b.clerk_user_id else None,
        )
        for b in budgets
    ]


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
        GuardAuditEvent.budget_eligible(),
    )
    if clerk_user_id is not None:
        q = q.filter(GuardAuditEvent.clerk_user_id == clerk_user_id)
    if ai_tool is not None:
        q = q.filter(GuardAuditEvent.ai_tool == ai_tool)
    if agent_identity_id is not None:
        q = q.filter(GuardAuditEvent.agent_identity_id == agent_identity_id)
    return float(q.scalar() or 0.0)


def _month_cost_groups(
    db: Session, ws_uuid: uuid.UUID,
) -> list[tuple[str | None, str | None, str | None, float]]:
    """One GROUP BY for the month: (clerk_user_id, ai_tool, agent_identity_id, cost).

    Replaces one SUM query per budget; each budget is then resolved in Python by
    `_cost_from_groups` with the same None-means-unfiltered semantics as
    `_current_month_cost`.
    """
    rows = db.query(
        GuardAuditEvent.clerk_user_id,
        GuardAuditEvent.ai_tool,
        GuardAuditEvent.agent_identity_id,
        func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0),
    ).filter(
        GuardAuditEvent.workspace_id == ws_uuid,
        GuardAuditEvent.ts >= _current_period_start(),
        GuardAuditEvent.budget_eligible(),
    ).group_by(
        GuardAuditEvent.clerk_user_id,
        GuardAuditEvent.ai_tool,
        GuardAuditEvent.agent_identity_id,
    ).all()
    return [(r[0], r[1], r[2], float(r[3] or 0.0)) for r in rows]


def _cost_from_groups(groups, budget: GuardSpendBudget) -> float:
    return sum(
        cost for uid, tool, agent, cost in groups
        if (budget.clerk_user_id is None or uid == budget.clerk_user_id)
        and (budget.ai_tool is None or tool == budget.ai_tool)
        and (budget.agent_identity_id is None or agent == budget.agent_identity_id)
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
