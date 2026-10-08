"""
GET  /guard/spend                  — spend summary for workspace (current calendar month)
GET  /guard/spend/sessions         — list sessions with totals
POST /guard/spend/budgets          — create or update a budget for user or workspace-wide
GET  /guard/spend/budgets          — list all budgets with current month usage
GET  /guard/spend/budget-check     — hard-cap check called by the guard hook (no Clerk auth)

Endpoints live in ``spend_summary``, ``spend_budgets`` and
``spend_budget_check``; shared schemas/helpers in ``spend_common``. This
module aggregates the routers in the original registration order and
re-exports the moved names.
"""
from fastapi import APIRouter

from app.modules.guard.routers.spend_common import (  # noqa: F401 — re-exports
    BudgetCheckOut, BudgetCreate, BudgetOut, DeveloperSpend, ModelSpend, ProviderSpend,
    ReservationScopeOut, SessionOut, SpendSummary, ToolSpend, _current_period_start,
    _next_period_start, _now, _org_ws_subquery, _parse_period_start, _period_label,
)
from app.modules.guard.routers.spend_summary import (  # noqa: F401 — re-exports
    _get_spend_summary_inner, _log, get_spend_summary, list_sessions,
)
from app.modules.guard.routers.spend_budgets import (  # noqa: F401 — re-exports
    _audit_budget_change, _budget_out, _current_month_cost, delete_budget, list_budgets,
    upsert_budget,
)
from app.modules.guard.routers.spend_budget_check import (  # noqa: F401 — re-exports
    budget_check, list_reservations_for_request,
)
from app.modules.guard.routers import spend_budget_check as _spend_budget_check
from app.modules.guard.routers import spend_budgets as _spend_budgets
from app.modules.guard.routers import spend_summary as _spend_summary

router = APIRouter()
router.include_router(_spend_summary.router)
router.include_router(_spend_budgets.router)
router.include_router(_spend_budget_check.router)
