"""#1302 — Lens actor: update the monthly USD limit on a spend budget.

Two-step: `propose` validates the budget id + new limit and resolves the
existing row's context (workspace-wide vs per-user) for the confirm card.
`execute` writes the new `monthly_limit_usd`, commits, and records a
hash-chained audit entry via the same helper the HTTP upsert uses.
"""
from __future__ import annotations

import uuid as _uuid
from typing import Any

import structlog

from app.modules.glens.actor.registry import default_action_registry
from app.modules.glens.actor.types import ActionCtx, ActionSpec, ProposeResult

log = structlog.get_logger()


def _propose_update_budget(ctx: ActionCtx, args: dict[str, Any]) -> ProposeResult:
    budget_id = str(args.get("budget_id") or "").strip()
    if not budget_id:
        return ProposeResult(rejected=True, reason="budget_id required",
                             summary="", resolved_input={})

    try:
        bud_uuid = _uuid.UUID(budget_id)
    except ValueError:
        return ProposeResult(rejected=True, reason=f"'{budget_id}' is not a valid UUID",
                             summary="", resolved_input={})

    try:
        ws_uuid = _uuid.UUID(ctx.workspace_id)
    except ValueError:
        return ProposeResult(rejected=True, reason="Invalid workspace",
                             summary="", resolved_input={})

    limit_raw = args.get("monthly_limit_usd")
    try:
        limit = float(limit_raw)
    except (TypeError, ValueError):
        return ProposeResult(rejected=True, reason="monthly_limit_usd must be a number",
                             summary="", resolved_input={})
    if limit < 0:
        return ProposeResult(rejected=True, reason="monthly_limit_usd cannot be negative",
                             summary="", resolved_input={})

    from app.modules.guard.models import GuardSpendBudget

    budget = ctx.db.query(GuardSpendBudget).filter(
        GuardSpendBudget.id == bud_uuid,
        GuardSpendBudget.workspace_id == ws_uuid,
    ).first()
    if not budget:
        return ProposeResult(
            rejected=True,
            reason=f"No budget matches id '{budget_id}' in this workspace",
            summary="", resolved_input={},
        )

    target = budget.clerk_user_id or "workspace-wide"
    old_limit = float(budget.monthly_limit_usd)
    summary = f"Update {target} monthly budget: ${old_limit:.2f} → ${limit:.2f}"

    return ProposeResult(
        summary=summary,
        resolved_input={
            "budget_id": str(budget.id),
            "monthly_limit_usd": limit,
            "old_limit_usd": old_limit,
            "clerk_user_id": budget.clerk_user_id,
        },
    )


def _execute_update_budget(ctx: ActionCtx, resolved: dict[str, Any]) -> dict[str, Any]:
    """Update monthly_limit_usd on the budget row and record an audit entry.

    Bypasses the HTTP upsert endpoint (which expects a full BudgetCreate
    body); we only mutate one field so a direct row update is cleaner."""
    from app.modules.guard.models import GuardSpendBudget
    from app.modules.guard.routers.spend import _audit_budget_change

    bud_uuid = _uuid.UUID(resolved["budget_id"])
    ws_uuid = _uuid.UUID(ctx.workspace_id)

    budget = ctx.db.query(GuardSpendBudget).filter(
        GuardSpendBudget.id == bud_uuid,
        GuardSpendBudget.workspace_id == ws_uuid,
    ).first()
    if not budget:
        raise ValueError(f"budget {bud_uuid} disappeared between propose and execute")

    old = float(budget.monthly_limit_usd)
    new = float(resolved["monthly_limit_usd"])
    budget.monthly_limit_usd = new
    ctx.db.commit()

    _audit_budget_change(
        ctx.db, ws_uuid, resolved.get("clerk_user_id"),
        "budget_updated", f"monthly {old}→{new}",
    )

    return {
        "budget_id": str(budget.id),
        "monthly_limit_usd": new,
        "old_limit_usd": old,
    }


default_action_registry.register(ActionSpec(
    name="update_budget",
    guard_permission="guard.spend.budgets.edit",
    propose=_propose_update_budget,
    execute=_execute_update_budget,
    description=(
        "Update the monthly USD limit on a spend budget. Two-step: returns "
        "a pending action for the user to confirm; the confirm click writes "
        "the new limit + a hash-chained audit entry."
    ),
))
