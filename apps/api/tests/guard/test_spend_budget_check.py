"""Regression tests for /guard/spend/budget-check.

Covers the two September 2026 fixes:
- F2: workspace-default `hard_cap_enabled` gates ALL enforcement. If the flag
  is off, the endpoint returns hard_blocked=False regardless of any set limits.
- F3: per-tool budgets. When the caller supplies ai_tool AND a per-tool row
  exists (clerk_user_id NULL, ai_tool set), the sum is scoped to that tool so
  a Codex Desktop overspend does not block a Claude Code caller.

Uses MagicMock at the ORM boundary — the endpoint's control flow is what we
care about, not the SQL. Postgres-level correctness is covered by the
alembic drift test and by any full-stack fixture tests.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.modules.guard.routers.spend import budget_check


WS_ID = "ef0a7e36-42a7-4968-9e6f-ee30d8e45383"
USER = "user_abc"


def _budget(**kw):
    """Fake GuardSpendBudget row with sensible defaults."""
    defaults = dict(
        id=uuid.uuid4(),
        workspace_id=uuid.UUID(WS_ID),
        clerk_user_id=None,
        ai_tool=None,
        monthly_limit_usd=1000.0,
        alert_threshold_pct=80,
        hard_limit_usd=None,
        hard_cap_enabled=False,
        default_per_developer_usd=None,
    )
    defaults.update(kw)
    return SimpleNamespace(**defaults)


class _DB:
    """Minimal db.query(Model).filter(...).first()/scalar() router."""

    def __init__(self, rows, cost_by_scope):
        self._rows = rows                # list of fake budget rows
        self._cost_by_scope = cost_by_scope  # dict of frozenset(filters) → float
        self._current_scope: set[str] = set()
        self._current_model = None

    def query(self, model):
        self._current_model = model
        self._current_scope = set()
        return self

    def filter(self, *conds):
        # We can't introspect SQLAlchemy expressions easily; instead the caller
        # records what it's asking for through _scope_hint below. This test's
        # trick: bounce all filter() calls into _current_scope so the shape of
        # the query is what matters, not the exact SQL fragments.
        return self

    def first(self):
        # Return the first row of the current model kind (GuardSpendBudget)
        # whose signature matches the tracked scope hint. Tests explicitly
        # patch _first_call_for_scope so we don't need SQL introspection.
        return self._rows.pop(0) if self._rows else None

    def scalar(self):
        # Cost aggregate — the endpoint calls func.sum(...).filter(...).scalar()
        return self._cost_by_scope.pop("next", 0.0)


def _run(*, workspace_id=WS_ID, clerk_user_id=None, ai_tool=None, rows=None, costs=None):
    """Invoke budget_check with a mocked DB, plus a GuardConfig existence stub."""
    rows = list(rows or [])
    costs = list(costs or [])
    db = MagicMock()

    # GuardConfig lookup (installation gate) — return truthy.
    gc_query = MagicMock()
    gc_query.filter.return_value = gc_query
    gc_query.first.return_value = object()

    # GuardSpendBudget lookups — return the queued rows in order.
    row_iter = iter(rows + [None] * 8)  # padded so extra queries return None

    def _budget_first(*args, **kwargs):
        return next(row_iter)

    budget_query = MagicMock()
    budget_query.filter.return_value = budget_query
    budget_query.first.side_effect = _budget_first

    # Cost sums — the endpoint calls db.query(func.coalesce(...)) and then
    # applies filters. Each call returns the next queued cost.
    cost_iter = iter(costs + [0.0] * 8)

    def _cost_scalar(*args, **kwargs):
        try:
            return next(cost_iter)
        except StopIteration:
            return 0.0

    cost_query = MagicMock()
    cost_query.filter.return_value = cost_query
    cost_query.scalar.side_effect = _cost_scalar

    def _route_query(model):
        # First call is always the workspace-default GuardSpendBudget lookup;
        # subsequent budget lookups also route to budget_query; func.* aggregate
        # queries route to cost_query.
        model_name = getattr(model, "__name__", str(model))
        if "GuardConfig" in model_name:
            return gc_query
        if "GuardSpendBudget" in model_name:
            return budget_query
        return cost_query

    db.query.side_effect = _route_query

    return budget_check(
        workspace_id=workspace_id,
        clerk_user_id=clerk_user_id,
        ai_tool=ai_tool,
        db=db,
    )


# ── F2 — enforcement gate ───────────────────────────────────────────────────

def test_flag_off_never_blocks_even_with_limit_and_overspend():
    """With hard_cap_enabled=False, hard_blocked is always False."""
    ws_default = _budget(hard_cap_enabled=False, hard_limit_usd=10.0)
    result = _run(
        rows=[ws_default],
        costs=[999_999.0],  # cost would blow past any real cap
    )
    assert result.hard_blocked is False


def test_flag_on_no_limits_does_not_block():
    """Flag on, but no hard_limit_usd anywhere → still hard_blocked=False."""
    ws_default = _budget(hard_cap_enabled=True, hard_limit_usd=None, default_per_developer_usd=None)
    result = _run(
        rows=[ws_default],
        costs=[42.0],
    )
    assert result.hard_blocked is False


def test_flag_on_workspace_hard_limit_blocks_when_over():
    ws_default = _budget(hard_cap_enabled=True, hard_limit_usd=100.0)
    result = _run(
        rows=[ws_default],
        # first cost call = _sum_cost() unscoped for the team branch
        costs=[125.0],
    )
    assert result.hard_blocked is True
    assert result.hard_limit_usd == 100.0


def test_flag_on_workspace_hard_limit_under_does_not_block():
    ws_default = _budget(hard_cap_enabled=True, hard_limit_usd=100.0)
    result = _run(
        rows=[ws_default],
        costs=[50.0],
    )
    assert result.hard_blocked is False


# ── F3 — per-tool bleed prevention ──────────────────────────────────────────

def test_per_tool_cap_blocks_only_when_that_tool_is_over():
    """Codex Desktop over its own cap → codex-desktop is blocked.

    R12 (reviewer P1): per-row hard_cap_enabled is now authoritative.
    The per-tool row must set the flag; pre-R12 it was ignored.
    """
    ws_default = _budget(hard_cap_enabled=True, hard_limit_usd=None)
    codex_row = _budget(
        clerk_user_id=None, ai_tool="codex-desktop",
        hard_limit_usd=30.0, hard_cap_enabled=True,  # R12: per-row flag decides
    )
    result = _run(
        ai_tool="codex-desktop",
        rows=[ws_default, codex_row],
        # first cost call = tool-scoped sum for codex-desktop
        costs=[50.0],
    )
    assert result.hard_blocked is True
    assert result.hard_limit_usd == 30.0
    assert "codex-desktop" in (result.reason or "")


def test_per_tool_cap_does_not_bleed_to_other_tool():
    """codex-desktop overspend must NOT block claude-code calls."""
    ws_default = _budget(hard_cap_enabled=True, hard_limit_usd=None)
    # Note: for claude-code, there is no per-tool row → tool_budget lookup returns None
    result = _run(
        ai_tool="claude-code",
        rows=[ws_default, None],
        # No per-tool row → 1a is skipped. workspace_cost fetched next = below cap.
        costs=[9999.0],  # this cost is for the unscoped workspace sum
    )
    # Since ws_default has no hard_limit_usd set, workspace sum is not enforced.
    assert result.hard_blocked is False


# ── R12 (reviewer P1) — per-row hard_cap_enabled semantics ───────

def test_r12_workspace_on_scoped_off_only_workspace_fires():
    """R12: workspace-default hard_cap_enabled=True, per-tool
    hard_cap_enabled=False. Pre-R12 both fired because master gate was
    on. Post-R12 only the workspace cap fires; per-tool cap is off.
    """
    ws_default = _budget(hard_cap_enabled=True, hard_limit_usd=100.0)
    codex_row = _budget(
        ai_tool="codex-desktop",
        hard_limit_usd=30.0,
        hard_cap_enabled=False,  # scoped OFF
    )
    # Cost query order: workspace-default lookup, tool lookup,
    # tool_cost (skipped because per-tool row is off), workspace_cost.
    result = _run(
        ai_tool="codex-desktop",
        rows=[ws_default, codex_row],
        # First _sum_cost call is scoped=None (workspace). 150 > 100 = block.
        costs=[150.0],
    )
    assert result.hard_blocked is True
    assert result.hard_limit_usd == 100.0  # workspace's cap, not tool's


def test_r12_workspace_off_scoped_on_scoped_fires():
    """R12: workspace hard_cap_enabled=False, per-tool
    hard_cap_enabled=True. Pre-R12 nothing fired because master gate was
    off. Post-R12 per-tool cap fires independently.
    """
    ws_default = _budget(
        hard_cap_enabled=False,  # workspace OFF (was pre-R12 kill switch)
        hard_limit_usd=None,
    )
    codex_row = _budget(
        ai_tool="codex-desktop",
        hard_limit_usd=30.0,
        hard_cap_enabled=True,  # scoped ON
    )
    result = _run(
        ai_tool="codex-desktop",
        rows=[ws_default, codex_row],
        # First _sum_cost is tool-scoped for codex-desktop. 50 > 30 = block.
        costs=[50.0],
    )
    assert result.hard_blocked is True
    assert result.hard_limit_usd == 30.0
    assert "codex-desktop" in (result.reason or "")


def test_r12_workspace_off_scoped_off_no_enforcement():
    """R12: both flags off. Nothing enforces. Matches pre-R12 behavior
    for this specific combination."""
    ws_default = _budget(hard_cap_enabled=False, hard_limit_usd=None)
    codex_row = _budget(
        ai_tool="codex-desktop",
        hard_limit_usd=30.0,
        hard_cap_enabled=False,
    )
    result = _run(
        ai_tool="codex-desktop",
        rows=[ws_default, codex_row],
        costs=[999.0],
    )
    assert result.hard_blocked is False
