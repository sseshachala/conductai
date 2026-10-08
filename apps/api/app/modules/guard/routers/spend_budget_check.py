"""ConductGuard spend — hook budget check and per-request reservation endpoints."""

import uuid
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session
from fastapi import HTTPException
from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.modules.guard.models import BudgetReservation, GuardAuditEvent, GuardConfig, GuardSpendBudget
from app.modules.guard.routers.spend_common import (
    BudgetCheckOut,
    ReservationScopeOut,
    _current_period_start,
)

router = APIRouter(prefix="/guard/spend", tags=["guard"])


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
            deleted_agent_identity_id=r.deleted_agent_identity_id,
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
