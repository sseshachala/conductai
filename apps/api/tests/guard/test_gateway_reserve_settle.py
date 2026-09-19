"""PR-A2a — reserve/settle helpers in gateway_lifecycle.

Verifies the semantics-only pieces of the multi-scope budget reservation
flow. Dark: these helpers are not wired into gateway_handler yet (PR-A2b).

Key contracts we prove here:

  1. Fail-CLOSED on ambiguity for hard caps: NOT_READY / REDIS_DOWN /
     DB error must return non-ACCEPTED outcomes so the caller rejects.
  2. Empty-list ACCEPTED is a valid dispatch-allow outcome (no hard cap).
  3. Ledger-disabled short-circuits to DISABLED so pre-PR-A behavior
     stays intact when the flag is off.
  4. Settlement respects the dispatched boundary:
      - not dispatched -> release_all (safe refund)
      - dispatched + actual_cents=int -> commit_all
      - dispatched + actual_cents=None -> pending_reconciler (never release)
  5. Empty reservations at settle time is a no-op.
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.modules.guard.gateway_lifecycle import (
    ReserveOutcome,
    SettleAction,
    reserve_budgets_for_request,
    settle_reservations,
)


WORKSPACE_ID = str(uuid.uuid4())
AGENT_A = "agent-aaaa-1111"


class _FakeBudget:
    def __init__(self, *, hard_cap_enabled=True, hard_limit_usd=1.0, ai_tool=None):
        self.hard_cap_enabled = hard_cap_enabled
        self.hard_limit_usd = hard_limit_usd
        self.ai_tool = ai_tool


class _FakeReservation:
    def __init__(self, rid):
        self.reservation_id = rid


# ── reserve_budgets_for_request ─────────────────────────────────────

def test_reserve_disabled_when_ledger_flag_off():
    """BUDGET_LEDGER_ENABLED=false -> DISABLED, so callers preserve
    pre-PR-A behavior (post-hoc spend tracking, no pre-flight block)."""
    with patch("app.core.budget_ledger.enabled", return_value=False):
        result = reserve_budgets_for_request(
            db=MagicMock(),
            workspace_id=WORKSPACE_ID,
            agent_identity_id=AGENT_A,
            transport="gateway",
            client_tool="cursor",
            clerk_user_id=None,
            estimated_cents=50,
            request_id=str(uuid.uuid4()),
        )
    assert result.outcome is ReserveOutcome.DISABLED
    assert result.reservations is None


def test_reserve_invalid_workspace_id_returns_db_error():
    """Malformed workspace_id must NOT fail-open. Reject early."""
    with patch("app.core.budget_ledger.enabled", return_value=True):
        result = reserve_budgets_for_request(
            db=MagicMock(),
            workspace_id="not-a-uuid",
            agent_identity_id=AGENT_A,
            transport="gateway",
            client_tool=None,
            clerk_user_id=None,
            estimated_cents=50,
            request_id=str(uuid.uuid4()),
        )
    assert result.outcome is ReserveOutcome.DB_ERROR


def test_reserve_no_applicable_budgets_returns_accepted_no_hard_cap():
    """Workspace has zero hard-capped budgets -> ACCEPTED_NO_HARD_CAP.
    Caller allows dispatch unconditionally."""
    from app.core.budget_ledger import BudgetDecision

    fake_ledger = MagicMock()
    fake_ledger.reserve_all.return_value = (BudgetDecision.ACCEPTED, [], None)
    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger), \
         patch("app.modules.guard.spend_lookup.lookup_applicable_budgets",
               return_value=[]):
        result = reserve_budgets_for_request(
            db=MagicMock(),
            workspace_id=WORKSPACE_ID,
            agent_identity_id=AGENT_A,
            transport="gateway",
            client_tool="cursor",
            clerk_user_id=None,
            estimated_cents=50,
            request_id=str(uuid.uuid4()),
        )
    assert result.outcome is ReserveOutcome.ACCEPTED_NO_HARD_CAP
    assert result.reservations == []


def test_reserve_with_hard_caps_accepted_returns_reservations():
    from app.core.budget_ledger import BudgetDecision

    reservations = [_FakeReservation("r1"), _FakeReservation("r2")]
    fake_ledger = MagicMock()
    fake_ledger.reserve_all.return_value = (BudgetDecision.ACCEPTED, reservations, None)
    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger), \
         patch("app.modules.guard.spend_lookup.lookup_applicable_budgets",
               return_value=[_FakeBudget(), _FakeBudget(ai_tool="gateway")]):
        result = reserve_budgets_for_request(
            db=MagicMock(),
            workspace_id=WORKSPACE_ID,
            agent_identity_id=AGENT_A,
            transport="gateway",
            client_tool="cursor",
            clerk_user_id=None,
            estimated_cents=50,
            request_id=str(uuid.uuid4()),
        )
    assert result.outcome is ReserveOutcome.ACCEPTED_WITH_RESERVATIONS
    assert result.reservations == reservations


def test_reserve_exceeded_is_fail_closed_with_refusing_budget_surfaced():
    from app.core.budget_ledger import BudgetDecision

    refusing = _FakeBudget(ai_tool="cursor", hard_limit_usd=0.01)
    fake_ledger = MagicMock()
    fake_ledger.reserve_all.return_value = (BudgetDecision.EXCEEDED, None, refusing)
    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger), \
         patch("app.modules.guard.spend_lookup.lookup_applicable_budgets",
               return_value=[refusing]):
        result = reserve_budgets_for_request(
            db=MagicMock(),
            workspace_id=WORKSPACE_ID,
            agent_identity_id=AGENT_A,
            transport="gateway",
            client_tool="cursor",
            clerk_user_id=None,
            estimated_cents=50,
            request_id=str(uuid.uuid4()),
        )
    assert result.outcome is ReserveOutcome.EXCEEDED
    assert result.refusing_budget is refusing
    assert result.error == "budget cap exceeded"


def test_reserve_not_ready_is_fail_closed():
    """Cold-worker reconciler-not-yet-run must NOT allow paid dispatch."""
    from app.core.budget_ledger import BudgetDecision

    fake_ledger = MagicMock()
    fake_ledger.reserve_all.return_value = (BudgetDecision.NOT_READY, None, None)
    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger), \
         patch("app.modules.guard.spend_lookup.lookup_applicable_budgets",
               return_value=[_FakeBudget()]):
        result = reserve_budgets_for_request(
            db=MagicMock(),
            workspace_id=WORKSPACE_ID,
            agent_identity_id=AGENT_A,
            transport="gateway",
            client_tool=None,
            clerk_user_id=None,
            estimated_cents=50,
            request_id=str(uuid.uuid4()),
        )
    assert result.outcome is ReserveOutcome.NOT_READY


def test_reserve_redis_down_is_fail_closed():
    """Redis outage on a hard-capped request must reject, never fail-open."""
    from app.core.budget_ledger import BudgetDecision

    fake_ledger = MagicMock()
    fake_ledger.reserve_all.return_value = (BudgetDecision.REDIS_DOWN, None, None)
    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger), \
         patch("app.modules.guard.spend_lookup.lookup_applicable_budgets",
               return_value=[_FakeBudget()]):
        result = reserve_budgets_for_request(
            db=MagicMock(),
            workspace_id=WORKSPACE_ID,
            agent_identity_id=AGENT_A,
            transport="gateway",
            client_tool=None,
            clerk_user_id=None,
            estimated_cents=50,
            request_id=str(uuid.uuid4()),
        )
    assert result.outcome is ReserveOutcome.REDIS_DOWN


def test_reserve_lookup_raise_is_fail_closed():
    """Any exception in the lookup path -> DB_ERROR, never accept."""
    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.modules.guard.spend_lookup.lookup_applicable_budgets",
               side_effect=RuntimeError("boom")):
        result = reserve_budgets_for_request(
            db=MagicMock(),
            workspace_id=WORKSPACE_ID,
            agent_identity_id=AGENT_A,
            transport="gateway",
            client_tool=None,
            clerk_user_id=None,
            estimated_cents=50,
            request_id=str(uuid.uuid4()),
        )
    assert result.outcome is ReserveOutcome.DB_ERROR


def test_reserve_ledger_reserve_all_raise_is_fail_closed():
    """reserve_all raising -> DB_ERROR."""
    fake_ledger = MagicMock()
    fake_ledger.reserve_all.side_effect = RuntimeError("boom")
    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger), \
         patch("app.modules.guard.spend_lookup.lookup_applicable_budgets",
               return_value=[_FakeBudget()]):
        result = reserve_budgets_for_request(
            db=MagicMock(),
            workspace_id=WORKSPACE_ID,
            agent_identity_id=AGENT_A,
            transport="gateway",
            client_tool=None,
            clerk_user_id=None,
            estimated_cents=50,
            request_id=str(uuid.uuid4()),
        )
    assert result.outcome is ReserveOutcome.DB_ERROR


# ── settle_reservations ─────────────────────────────────────────────

def test_settle_empty_list_is_noop():
    result = settle_reservations(
        db=MagicMock(),
        reservations=[],
        dispatched=True,
        actual_cents=42,
    )
    assert result.action is SettleAction.NOOP
    assert result.reservations_processed == 0


def test_settle_not_dispatched_releases_all():
    """No wire bytes flew — safe to refund all reservations."""
    reservations = [_FakeReservation("r1"), _FakeReservation("r2")]
    fake_ledger = MagicMock()
    with patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger):
        result = settle_reservations(
            db=MagicMock(),
            reservations=reservations,
            dispatched=False,
            actual_cents=None,
        )
    assert result.action is SettleAction.RELEASED
    assert result.reservations_processed == 2
    fake_ledger.release_all.assert_called_once()
    fake_ledger.commit_all.assert_not_called()


def test_settle_not_dispatched_ignores_actual_cents_and_releases():
    """dispatched=False beats actual_cents — never commit when dispatch
    didn't happen."""
    reservations = [_FakeReservation("r1")]
    fake_ledger = MagicMock()
    with patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger):
        result = settle_reservations(
            db=MagicMock(),
            reservations=reservations,
            dispatched=False,
            actual_cents=999,  # ignored — dispatched is False
        )
    assert result.action is SettleAction.RELEASED
    fake_ledger.release_all.assert_called_once()
    fake_ledger.commit_all.assert_not_called()


def test_settle_dispatched_with_actual_cents_commits():
    reservations = [_FakeReservation("r1"), _FakeReservation("r2")]
    fake_ledger = MagicMock()
    with patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger):
        result = settle_reservations(
            db=MagicMock(),
            reservations=reservations,
            dispatched=True,
            actual_cents=47,
        )
    assert result.action is SettleAction.COMMITTED
    assert result.reservations_processed == 2
    fake_ledger.commit_all.assert_called_once()
    call = fake_ledger.commit_all.call_args
    assert call.kwargs["actual_cents"] == 47
    fake_ledger.release_all.assert_not_called()


def test_reserve_accepts_and_forwards_estimated_micros():
    # Regression: gateway_handler passes ``estimated_micros=`` at every call
    # site (R9). If this helper's signature drops it, every gateway request
    # 503s with ``reserve raised: TypeError``. Cover that the kwarg is
    # accepted AND forwarded to reserve_all so microdollar precision reaches
    # the ledger.
    fake_ledger = MagicMock()
    fake_ledger.reserve_all.return_value = (
        __import__("app.core.budget_ledger", fromlist=["BudgetDecision"]).BudgetDecision.ACCEPTED,
        [],
        None,
    )
    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.core.budget_ledger.enabled_for", return_value=True), \
         patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger), \
         patch(
             "app.modules.guard.spend_lookup.lookup_applicable_budgets",
             return_value=[],
         ):
        result = reserve_budgets_for_request(
            db=MagicMock(),
            workspace_id=WORKSPACE_ID,
            agent_identity_id=AGENT_A,
            transport="gateway",
            client_tool="cursor",
            clerk_user_id=None,
            estimated_cents=1,
            estimated_micros=7_500,
            request_id=str(uuid.uuid4()),
        )
    assert result.outcome is ReserveOutcome.ACCEPTED_NO_HARD_CAP
    call = fake_ledger.reserve_all.call_args
    assert call.kwargs["estimated_micros"] == 7_500


def test_settle_dispatched_without_actual_cents_marks_pending_reconciler():
    """LOAD-BEARING: bytes flew, outcome unknown -> DO NOT release.
    Reconciler owns cleanup via lease expiry."""
    reservations = [_FakeReservation("r1")]
    fake_ledger = MagicMock()
    with patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger):
        result = settle_reservations(
            db=MagicMock(),
            reservations=reservations,
            dispatched=True,
            actual_cents=None,
        )
    assert result.action is SettleAction.PENDING_RECONCILER
    assert result.reservations_processed == 1
    fake_ledger.release_all.assert_not_called()
    fake_ledger.commit_all.assert_not_called()
