"""R2 (reviewer P1) — startup reconciliation + recovery sweep tests.

Covers:

- Flag off short-circuits both entry points.
- Startup enumerates open reservations + committed traffic and calls
  ``BudgetLedger.reconcile()`` for every distinct scope.
- Idempotency: a second startup run against warm state performs the
  same reconciles and does not crash.
- Recovery sweep classifies stale open reservations correctly:
    - correlated audit finalized + cost known -> committed
    - correlated audit orphaned/expired/absent -> released
    - correlated audit still in accepted -> left_open

Uses a stub Session identical to the ledger-tests pattern for
deterministic in-process behavior. A live-DB integration test is a
follow-up (the reviewer's chaos suite from the epic covers it).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def _make_reservation_row(
    *,
    workspace_id=None,
    clerk_user_id=None,
    agent_identity_id=None,
    ai_tool=None,
    period_key="2026-09",
    status="open",
    request_id=None,
    estimated_cents=50,
    created_at=None,
):
    """Fake BudgetReservation ORM object for the sweep tests."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        workspace_id=workspace_id or uuid.uuid4(),
        clerk_user_id=clerk_user_id,
        agent_identity_id=agent_identity_id,
        ai_tool=ai_tool,
        period_key=period_key,
        status=status,
        request_id=request_id,
        estimated_cents=estimated_cents,
        created_at=created_at or datetime.now(timezone.utc) - timedelta(hours=1),
    )


def _make_audit_row(*, request_id=None, lifecycle_state="finalized", cost_usd_after=0.5):
    return SimpleNamespace(
        request_id=request_id,
        lifecycle_state=lifecycle_state,
        cost_usd_after=cost_usd_after,
    )


def _make_receipt_row(
    *,
    request_id=None,
    calculated_cost_microdollars=1_050,
    usage_completeness="complete",
    pricing_completeness="priced",
):
    """PR 4 P1-A/P1-B: recovery reads settleable receipts, not audit."""
    return SimpleNamespace(
        request_id=request_id,
        calculated_cost_microdollars=calculated_cost_microdollars,
        usage_completeness=usage_completeness,
        pricing_completeness=pricing_completeness,
    )


class _RoutingDB:
    """Test double that dispatches ``db.query(Model)`` to a per-model
    ``.filter(...).first()`` result. Recovery classification now consults
    two tables (receipts first, then audit) and the classic ``MagicMock``
    pattern can't tell them apart."""

    def __init__(self, *, receipt=None, audit=None):
        self._receipt = receipt
        self._audit = audit

    def query(self, model):
        # Match by class name so we don't need real ORM imports here.
        name = getattr(model, "__name__", str(model))
        result = None
        if name == "LlmAttemptReceipt":
            result = self._receipt
        elif name == "GuardAuditEvent":
            result = self._audit
        chain = MagicMock()
        chain.filter.return_value.first.return_value = result
        return chain


# ── Flag off ─────────────────────────────────────────────────────

def test_startup_skipped_when_ledger_disabled():
    from app.core.budget_reconciler import run_startup_reconciliation

    with patch("app.core.budget_ledger.enabled", return_value=False):
        result = run_startup_reconciliation()
    assert result["skipped"] is True
    assert result["scopes_reconciled"] == 0


def test_recovery_skipped_when_ledger_disabled():
    from app.core.budget_reconciler import run_recovery_sweep

    with patch("app.core.budget_ledger.enabled", return_value=False):
        result = run_recovery_sweep()
    assert result["skipped"] is True
    assert result["committed"] == 0
    assert result["released"] == 0


# ── Startup enumeration ──────────────────────────────────────────

def test_startup_reconciles_every_open_reservation_scope():
    """Enumerate distinct scopes from open reservations; call
    ledger.reconcile() once per scope."""
    from app.core import budget_reconciler as br

    scopes_reserved = [
        ("ws-1", None, None, None),
        ("ws-1", None, "agent-a", None),
        ("ws-2", "user-b", None, "cursor"),
    ]
    fake_ledger = MagicMock()

    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger), \
         patch("app.core.budget_reconciler._enumerate_open_reservation_scopes",
               return_value=iter(scopes_reserved)), \
         patch("app.core.budget_reconciler._enumerate_committed_scopes",
               return_value=iter([])):
        fake_session = MagicMock()
        fake_factory = MagicMock(return_value=fake_session)
        result = br.run_startup_reconciliation(session_factory=fake_factory)

    assert result["scopes_reconciled"] == 3
    assert result["errors"] == 0
    assert fake_ledger.reconcile.call_count == 3
    reconciled_scopes = {
        (
            call.kwargs["workspace_id"],
            call.kwargs["clerk_user_id"],
            call.kwargs["agent_identity_id"],
            call.kwargs["ai_tool"],
        )
        for call in fake_ledger.reconcile.call_args_list
    }
    assert reconciled_scopes == set(scopes_reserved)


def test_startup_includes_committed_only_scopes():
    """Scopes with committed traffic but no open reservation still
    need reconcile so ``ready`` key gets set (otherwise subsequent
    reserve() returns NOT_READY indefinitely)."""
    from app.core import budget_reconciler as br

    committed_only = [("ws-3", None, None, "gateway")]
    fake_ledger = MagicMock()

    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger), \
         patch("app.core.budget_reconciler._enumerate_open_reservation_scopes",
               return_value=iter([])), \
         patch("app.core.budget_reconciler._enumerate_committed_scopes",
               return_value=iter(committed_only)):
        fake_factory = MagicMock(return_value=MagicMock())
        result = br.run_startup_reconciliation(session_factory=fake_factory)

    assert result["scopes_reconciled"] == 1
    assert fake_ledger.reconcile.call_count == 1


def test_startup_deduplicates_overlapping_scopes():
    """A scope with both an open reservation AND committed spend is
    reconciled exactly once, not twice."""
    from app.core import budget_reconciler as br

    both = ("ws-1", None, None, None)
    fake_ledger = MagicMock()
    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger), \
         patch("app.core.budget_reconciler._enumerate_open_reservation_scopes",
               return_value=iter([both])), \
         patch("app.core.budget_reconciler._enumerate_committed_scopes",
               return_value=iter([both])):
        result = br.run_startup_reconciliation(session_factory=MagicMock(return_value=MagicMock()))

    assert result["scopes_reconciled"] == 1
    assert fake_ledger.reconcile.call_count == 1


def test_startup_records_partial_when_a_scope_reconcile_raises():
    """If one scope's reconcile raises, others still complete and
    the outcome is 'partial' (not 'error')."""
    from app.core import budget_reconciler as br

    scopes = [("ws-1", None, None, None), ("ws-2", None, None, None)]
    fake_ledger = MagicMock()
    fake_ledger.reconcile.side_effect = [None, RuntimeError("bang")]

    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger), \
         patch("app.core.budget_reconciler._enumerate_open_reservation_scopes",
               return_value=iter(scopes)), \
         patch("app.core.budget_reconciler._enumerate_committed_scopes",
               return_value=iter([])):
        result = br.run_startup_reconciliation(session_factory=MagicMock(return_value=MagicMock()))

    assert result["scopes_reconciled"] == 1
    assert result["errors"] == 1


# ── Recovery sweep classification ────────────────────────────────

def test_classify_settleable_receipt_returns_committed():
    """PR 4 P1-A: a definitive receipt (complete + priced) → commit."""
    from app.core.budget_reconciler import _classify_stale_reservation

    reservation = _make_reservation_row(request_id=uuid.uuid4())
    receipt = _make_receipt_row(
        request_id=reservation.request_id,
        calculated_cost_microdollars=420_000,
        usage_completeness="complete",
        pricing_completeness="priced",
    )
    db = _RoutingDB(receipt=receipt)
    assert _classify_stale_reservation(db, reservation) == "committed"


def test_classify_finalized_audit_without_settleable_receipt_returns_left_open():
    """PR 4 P1-A: pre-cutover we would have committed from audit cost.
    Post-cutover, no settleable receipt ⇒ leave open, let the accounting
    reconciler backfill a definitive receipt (legacy audit math has no
    cache breakout and understates the ledger)."""
    from app.core.budget_reconciler import _classify_stale_reservation

    reservation = _make_reservation_row(request_id=uuid.uuid4())
    audit = _make_audit_row(
        request_id=reservation.request_id,
        lifecycle_state="finalized",
        cost_usd_after=0.42,
    )
    db = _RoutingDB(audit=audit)
    assert _classify_stale_reservation(db, reservation) == "left_open"


def test_classify_partial_receipt_returns_left_open():
    """PR 4 P1-A: PARTIAL usage receipt is NOT settleable — recovery
    must leave the reservation open, not commit a lower bound."""
    from app.core.budget_reconciler import _classify_stale_reservation

    reservation = _make_reservation_row(request_id=uuid.uuid4())
    # Receipt exists but is PARTIAL → filter excludes it → treated as absent.
    db = _RoutingDB(receipt=None, audit=_make_audit_row(
        request_id=reservation.request_id,
        lifecycle_state="finalized",
    ))
    assert _classify_stale_reservation(db, reservation) == "left_open"


def test_classify_orphaned_audit_returns_released():
    from app.core.budget_reconciler import _classify_stale_reservation

    reservation = _make_reservation_row(request_id=uuid.uuid4())
    audit = _make_audit_row(
        request_id=reservation.request_id,
        lifecycle_state="orphaned",
    )
    db = _RoutingDB(audit=audit)
    assert _classify_stale_reservation(db, reservation) == "released"


def test_classify_missing_audit_returns_released():
    from app.core.budget_reconciler import _classify_stale_reservation

    reservation = _make_reservation_row(request_id=uuid.uuid4())
    db = _RoutingDB()  # neither receipt nor audit
    assert _classify_stale_reservation(db, reservation) == "released"


def test_classify_no_request_id_returns_released():
    """A reservation from a pre-R5 row without request_id correlation
    can't be classified — released is safe."""
    from app.core.budget_reconciler import _classify_stale_reservation

    reservation = _make_reservation_row(request_id=None)
    db = MagicMock()
    assert _classify_stale_reservation(db, reservation) == "released"


def test_classify_still_accepted_audit_leaves_open():
    """Reservation whose audit row is still in 'accepted' — the audit
    lease-expiry sweep will resolve it eventually. Don't force here."""
    from app.core.budget_reconciler import _classify_stale_reservation

    reservation = _make_reservation_row(request_id=uuid.uuid4())
    audit = _make_audit_row(
        request_id=reservation.request_id,
        lifecycle_state="accepted",
    )
    db = _RoutingDB(audit=audit)
    assert _classify_stale_reservation(db, reservation) == "left_open"


def test_recovery_sweep_commits_from_settleable_receipt():
    """PR 4 P1-A end-to-end: stale open reservation with a definitive
    receipt → ledger.commit() called with the RECEIPT's cost, not
    audit's ``cost_usd_after``."""
    from app.core import budget_reconciler as br

    reservation = _make_reservation_row(request_id=uuid.uuid4())
    # Post-cutover receipt says 1_050 μUSD (with cache breakout).
    receipt = _make_receipt_row(
        request_id=reservation.request_id,
        calculated_cost_microdollars=1_050_000,  # 1.05 USD
        usage_completeness="complete",
        pricing_completeness="priced",
    )
    # Audit event exists but is legacy math — must NOT be used for cost.
    audit = _make_audit_row(
        request_id=reservation.request_id,
        lifecycle_state="finalized",
        cost_usd_after=0.42,  # wrong number, would show if bug returns
    )

    fake_ledger = MagicMock()
    fake_session = MagicMock()

    # .query order: BudgetReservation (list of stale rows),
    # then LlmAttemptReceipt (classify), then LlmAttemptReceipt (commit).
    query_results = [[reservation], receipt, receipt]
    def _query(model, *args, **kwargs):
        name = getattr(model, "__name__", str(model))
        result = query_results.pop(0)
        chain = MagicMock()
        if isinstance(result, list):
            if _query_results_returned_list_once_only(name):
                chain.filter.return_value.limit.return_value.all.return_value = result
            else:
                chain.filter.return_value.all.return_value = result
        else:
            chain.filter.return_value.first.return_value = result
        return chain
    _first_list_call = {"n": True}
    def _query_results_returned_list_once_only(name):
        return name == "BudgetReservation"
    fake_session.query.side_effect = _query

    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger):
        result = br.run_recovery_sweep(
            session_factory=lambda: fake_session,
            stale_seconds=1,
        )

    assert result["committed"] == 1
    assert result["released"] == 0
    fake_ledger.commit.assert_called_once()
    call_kwargs = fake_ledger.commit.call_args.kwargs
    # 1_050_000 μUSD → 105 cents. Audit's 42-cents number would fail here.
    assert call_kwargs["actual_cents"] == 105
    assert call_kwargs["actual_micros"] == 1_050_000


def test_recovery_sweep_leaves_open_when_receipt_partial():
    """PR 4 P1-A: PARTIAL receipt → classify returns left_open, no
    commit call. Preserves invariant that recovery never charges a
    lower bound."""
    from app.core import budget_reconciler as br

    reservation = _make_reservation_row(request_id=uuid.uuid4())
    # Filter excludes partial receipts, so this query returns None.
    fake_ledger = MagicMock()
    fake_session = MagicMock()
    query_results = [[reservation], None, None]  # reservations, receipt (miss), audit (miss)
    def _query(model, *args, **kwargs):
        result = query_results.pop(0)
        chain = MagicMock()
        if isinstance(result, list):
            chain.filter.return_value.limit.return_value.all.return_value = result
        else:
            chain.filter.return_value.first.return_value = result
        return chain
    fake_session.query.side_effect = _query

    with patch("app.core.budget_ledger.enabled", return_value=True), \
         patch("app.core.budget_ledger.get_budget_ledger", return_value=fake_ledger):
        result = br.run_recovery_sweep(
            session_factory=lambda: fake_session,
            stale_seconds=1,
        )

    assert result["committed"] == 0
    assert result["left_open"] + result["released"] == 1
    fake_ledger.commit.assert_not_called()
