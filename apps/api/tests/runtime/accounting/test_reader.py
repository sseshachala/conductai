"""AccountingReader + SpendAggregate self-checks (#2209 Session 5).

Tests the aggregation logic + completeness surfacing without needing a
live Postgres. The SQL path itself is tested end-to-end in the Session 6
integration tests.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.runtime.accounting import (
    AggregateScope,
    SpendAggregate,
    aggregate_from_rows,
)
from app.runtime.accounting.contracts import (
    ExecutionOutcome,
    PricingCompleteness,
    UsageCompleteness,
)


@dataclass
class _FakeReceipt:
    """Minimal duck-typed receipt for aggregation tests."""

    request_id: uuid.UUID
    calculated_cost_microdollars: int
    reserved_microdollars: int
    total_input_tokens: int
    total_output_tokens: int
    uncached_input_tokens: int
    cache_read_tokens: int
    reasoning_output_tokens: int
    usage_completeness: str
    pricing_completeness: str
    execution_outcome: str


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _receipt(**overrides) -> _FakeReceipt:
    base = dict(
        request_id=uuid.uuid4(),
        calculated_cost_microdollars=1_000,
        reserved_microdollars=1_500,
        total_input_tokens=100,
        total_output_tokens=50,
        uncached_input_tokens=100,
        cache_read_tokens=0,
        reasoning_output_tokens=0,
        usage_completeness=UsageCompleteness.COMPLETE.value,
        pricing_completeness=PricingCompleteness.PRICED.value,
        execution_outcome=ExecutionOutcome.SUCCEEDED.value,
    )
    base.update(overrides)
    return _FakeReceipt(**base)


def test_empty_rows_returns_zero_aggregate():
    start = _now()
    end = start + timedelta(hours=1)
    agg = aggregate_from_rows(
        [], scope=AggregateScope.WORKSPACE, period_start=start, period_end=end
    )
    assert agg.receipt_count == 0
    assert agg.total_cost_microdollars == 0
    assert agg.has_partial_or_missing is False


def test_summed_receipts_produce_totals():
    start = _now()
    end = start + timedelta(hours=1)
    rows = [_receipt(calculated_cost_microdollars=c) for c in (1000, 2000, 3000)]
    agg = aggregate_from_rows(
        rows, scope=AggregateScope.WORKSPACE, period_start=start, period_end=end
    )
    assert agg.receipt_count == 3
    assert agg.total_cost_microdollars == 6000
    assert agg.total_cost_usd == Decimal("0.006")


def test_distinct_request_ids_counted():
    """Retries + fallbacks generate multiple receipts with the same request_id.
    request_count counts DISTINCT requests, receipt_count counts attempts."""
    start = _now()
    end = start + timedelta(hours=1)
    shared = uuid.uuid4()
    rows = [
        _receipt(request_id=shared),
        _receipt(request_id=shared),  # same request, retry
        _receipt(),  # different request
    ]
    agg = aggregate_from_rows(
        rows, scope=AggregateScope.WORKSPACE, period_start=start, period_end=end
    )
    assert agg.receipt_count == 3
    assert agg.request_count == 2


def test_completeness_breakdown_flags_partial_data():
    """Invariant #4: partial usage must be distinguishable in the aggregate."""
    start = _now()
    end = start + timedelta(hours=1)
    rows = [
        _receipt(),  # COMPLETE
        _receipt(usage_completeness=UsageCompleteness.PARTIAL.value),
        _receipt(usage_completeness=UsageCompleteness.UNAVAILABLE.value),
    ]
    agg = aggregate_from_rows(
        rows, scope=AggregateScope.WORKSPACE, period_start=start, period_end=end
    )
    assert agg.completeness_breakdown[UsageCompleteness.COMPLETE.value] == 1
    assert agg.completeness_breakdown[UsageCompleteness.PARTIAL.value] == 1
    assert agg.completeness_breakdown[UsageCompleteness.UNAVAILABLE.value] == 1
    assert agg.has_partial_or_missing is True


def test_unpriced_flagged_separately_from_priced_total():
    """Invariant #9: unknown-model attempts must not silently fold into the
    priced total. The aggregate exposes the count so Lens can surface it."""
    start = _now()
    end = start + timedelta(hours=1)
    rows = [
        _receipt(),  # PRICED
        _receipt(
            calculated_cost_microdollars=0,
            pricing_completeness=PricingCompleteness.UNPRICED.value,
        ),
    ]
    agg = aggregate_from_rows(
        rows, scope=AggregateScope.WORKSPACE, period_start=start, period_end=end
    )
    assert agg.has_unpriced_attempts is True
    assert agg.pricing_completeness_breakdown[PricingCompleteness.UNPRICED.value] == 1


def test_execution_outcome_breakdown():
    start = _now()
    end = start + timedelta(hours=1)
    rows = [
        _receipt(execution_outcome=ExecutionOutcome.SUCCEEDED.value),
        _receipt(execution_outcome=ExecutionOutcome.FAILED.value),
        _receipt(execution_outcome=ExecutionOutcome.REJECTED_PREFLIGHT.value),
    ]
    agg = aggregate_from_rows(
        rows, scope=AggregateScope.WORKSPACE, period_start=start, period_end=end
    )
    assert agg.execution_outcome_breakdown[ExecutionOutcome.SUCCEEDED.value] == 1
    assert agg.execution_outcome_breakdown[ExecutionOutcome.FAILED.value] == 1
    assert agg.execution_outcome_breakdown[ExecutionOutcome.REJECTED_PREFLIGHT.value] == 1


def test_reasoning_tokens_summed_but_not_added_to_cost():
    """Invariant #5: reasoning subset does not increase cost."""
    start = _now()
    end = start + timedelta(hours=1)
    rows = [
        _receipt(
            total_output_tokens=100,
            reasoning_output_tokens=30,
            calculated_cost_microdollars=1500,
        ),
        _receipt(
            total_output_tokens=200,
            reasoning_output_tokens=50,
            calculated_cost_microdollars=3000,
        ),
    ]
    agg = aggregate_from_rows(
        rows, scope=AggregateScope.WORKSPACE, period_start=start, period_end=end
    )
    assert agg.total_output_tokens == 300
    assert agg.total_reasoning_output_tokens == 80
    assert agg.total_cost_microdollars == 4500  # NOT 4500 + reasoning * anything


def test_cache_read_tokens_surfaced_for_savings_calculation():
    """Lens 'how much did caching save?' = f(uncached rate, cache_read rate, tokens).
    The aggregate exposes cache_read_tokens; Lens does the display math against
    the pricing snapshot the receipts were priced under."""
    start = _now()
    end = start + timedelta(hours=1)
    rows = [
        _receipt(
            total_input_tokens=1000,
            uncached_input_tokens=200,
            cache_read_tokens=800,
        ),
        _receipt(
            total_input_tokens=500,
            uncached_input_tokens=500,
            cache_read_tokens=0,
        ),
    ]
    agg = aggregate_from_rows(
        rows, scope=AggregateScope.WORKSPACE, period_start=start, period_end=end
    )
    assert agg.total_input_tokens == 1500
    assert agg.total_uncached_input_tokens == 700
    assert agg.total_cache_read_tokens == 800


def test_scope_value_recorded_in_result():
    start = _now()
    end = start + timedelta(hours=1)
    agg = aggregate_from_rows(
        [_receipt()],
        scope=AggregateScope.DEVELOPER,
        period_start=start,
        period_end=end,
        scope_value="user_abc",
    )
    assert agg.scope == {"developer_user_id": "user_abc"}


def test_aggregate_is_frozen():
    import pytest
    from dataclasses import FrozenInstanceError

    agg = aggregate_from_rows(
        [_receipt()],
        scope=AggregateScope.WORKSPACE,
        period_start=_now(),
        period_end=_now() + timedelta(hours=1),
    )
    with pytest.raises(FrozenInstanceError):
        agg.total_cost_microdollars = 999  # type: ignore[misc]


# #2209 Tier 1: ``test_legacy_cost_summed_for_shadow_delta`` was
# retired with the ``legacy_cost_microdollars`` column. The new engine
# is authoritative post-cutover; there is no legacy total to compare
# against.
