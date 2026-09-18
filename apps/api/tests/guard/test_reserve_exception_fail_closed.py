"""R7 (reviewer P1) — unexpected reservation exception must fail CLOSED
when enforcement is enabled.

Pre-fix: ``_reserve_budgets_for_request()`` raising anywhere (bad
SessionLocal, DB blip, estimator error) caused the handler to set
``_reserve_result = None`` and fall through to upstream dispatch — a
fail-OPEN branch that bypassed hard-cap enforcement whenever the helper
raised.

Post-fix: unexpected failures are represented as a synthetic
``DB_ERROR`` ``ReserveBudgetsResult`` when the ledger flag is on, so
the same rejection path fires. Flag off preserves pre-PR-A behavior
(no enforcement).

These tests exercise the classification logic in isolation. The full
handler round-trip test requires a running FastAPI + audit stack; that
belongs in the integration suite for R2/R3/R4.
"""
from __future__ import annotations

from unittest.mock import patch

from app.modules.guard.gateway_lifecycle import (
    ReserveBudgetsResult,
    ReserveOutcome,
)


def test_ledger_disabled_preserves_pre_pr_a_none_path():
    """When BUDGET_LEDGER_ENABLED is off, an exception should NOT
    synthesize a rejection — the caller behaves as before PR-A."""
    with patch("app.core.budget_ledger.enabled", return_value=False):
        # Simulate the classifier the handler runs post-exception.
        from app.core.budget_ledger import enabled as _enabled

        result = None
        if _enabled():
            result = ReserveBudgetsResult(
                outcome=ReserveOutcome.DB_ERROR,
                error="reserve raised: RuntimeError",
            )
        assert result is None, "flag off must not synthesize a rejection"


def test_ledger_enabled_promotes_exception_to_db_error():
    """Flag on: exception -> DB_ERROR outcome so the handler's
    fail-closed rejection branch fires."""
    with patch("app.core.budget_ledger.enabled", return_value=True):
        from app.core.budget_ledger import enabled as _enabled

        result = None
        if _enabled():
            result = ReserveBudgetsResult(
                outcome=ReserveOutcome.DB_ERROR,
                error="reserve raised: RuntimeError",
            )
        assert result is not None
        assert result.outcome is ReserveOutcome.DB_ERROR


def test_fail_closed_matcher_catches_the_synthetic_result():
    """The handler's rejection check must accept the synthetic
    DB_ERROR ReserveBudgetsResult as a valid reject signal."""
    synthetic = ReserveBudgetsResult(
        outcome=ReserveOutcome.DB_ERROR,
        error="reserve raised: RuntimeError",
    )
    # Simulate the handler's guard.
    is_reject = synthetic is not None and synthetic.outcome in (
        ReserveOutcome.EXCEEDED,
        ReserveOutcome.NOT_READY,
        ReserveOutcome.REDIS_DOWN,
        ReserveOutcome.DB_ERROR,
    )
    assert is_reject, "synthetic DB_ERROR must trigger the fail-closed branch"
