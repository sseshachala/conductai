"""Pure-Python accounting aggregation helpers (split from reader.py; re-exported there)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Iterable, Optional

from app.models.llm_attempt_receipt import LlmAttemptReceipt
from app.runtime.accounting.reader_types import (
    AggregateScope,
    CacheReadSavings,
    SpendAggregate,
)


def compute_cache_read_savings_for_receipt(
    receipt: LlmAttemptReceipt,
    *,
    uncached_rate_per_1m_usd: Decimal,
    cache_read_rate_per_1m_usd: Decimal,
) -> CacheReadSavings:
    """Gross cache-read savings for ONE receipt.

    Preferred entry point — callers should look up the rate card that
    matches ``receipt.pricing_version`` and ``receipt.model`` via
    ``PricingService.get_rate_card()``. That keeps the answer honest
    when a workspace's rate card changes mid-period or spans models.

    Formula: ``savings = (uncached_rate - cache_read_rate) × cache_read_tokens``.
    """
    read_tokens = int(receipt.cache_read_tokens or 0)
    uncached_tokens = int(receipt.uncached_input_tokens or 0)
    if read_tokens <= 0:
        return CacheReadSavings(
            cache_read_tokens=0,
            uncached_input_tokens=uncached_tokens,
            savings_microdollars=0,
            counterfactual_read_cost_microdollars=0,
        )
    delta_per_1m = uncached_rate_per_1m_usd - cache_read_rate_per_1m_usd
    savings_usd = Decimal(read_tokens) * delta_per_1m / Decimal(1_000_000)
    counterfactual_usd = (
        Decimal(read_tokens) * uncached_rate_per_1m_usd / Decimal(1_000_000)
    )
    return CacheReadSavings(
        cache_read_tokens=read_tokens,
        uncached_input_tokens=uncached_tokens,
        savings_microdollars=int((savings_usd * Decimal(1_000_000)).to_integral_value()),
        counterfactual_read_cost_microdollars=int(
            (counterfactual_usd * Decimal(1_000_000)).to_integral_value()
        ),
    )


def compute_cache_read_savings(
    total_cache_read_tokens: int,
    total_uncached_input_tokens: int,
    *,
    uncached_rate_per_1m_usd: Decimal,
    cache_read_rate_per_1m_usd: Decimal,
) -> CacheReadSavings:
    """Single-rate-pair helper for callers that already hold a
    single-model aggregate.

    Reviewer #6: caller MUST guarantee the token counts belong to one
    (model, pricing_version) slice. Aggregating across rate cards makes
    the answer nonsense. For multi-model queries, iterate receipts and
    sum ``compute_cache_read_savings_for_receipt`` results instead.
    """
    if total_cache_read_tokens <= 0:
        return CacheReadSavings(
            cache_read_tokens=0,
            uncached_input_tokens=int(total_uncached_input_tokens),
            savings_microdollars=0,
            counterfactual_read_cost_microdollars=0,
        )
    delta_per_1m = uncached_rate_per_1m_usd - cache_read_rate_per_1m_usd
    savings_usd = (
        Decimal(total_cache_read_tokens) * delta_per_1m / Decimal(1_000_000)
    )
    counterfactual_usd = (
        Decimal(total_cache_read_tokens) * uncached_rate_per_1m_usd / Decimal(1_000_000)
    )
    return CacheReadSavings(
        cache_read_tokens=int(total_cache_read_tokens),
        uncached_input_tokens=int(total_uncached_input_tokens),
        savings_microdollars=int(
            (savings_usd * Decimal(1_000_000)).to_integral_value()
        ),
        counterfactual_read_cost_microdollars=int(
            (counterfactual_usd * Decimal(1_000_000)).to_integral_value()
        ),
    )


# Back-compat alias. Session 6E docs pointed at this name.
compute_cache_savings = compute_cache_read_savings


def aggregate_from_rows(
    rows: Iterable[Any],
    *,
    scope: AggregateScope,
    period_start: datetime,
    period_end: datetime,
    scope_value: Optional[str] = None,
) -> SpendAggregate:
    """Aggregate a Python-side collection of receipt-like objects into one
    ``SpendAggregate``. Useful for tests + reconciliation harnesses without
    needing a live database round-trip.

    Any object exposing the receipt column names as attributes works
    (SQLAlchemy models, dataclasses, namedtuples).
    """
    receipt_count = 0
    request_ids: set[str] = set()
    total_cost = 0
    total_reserved = 0
    legacy_cost = 0
    input_tokens = 0
    output_tokens = 0
    uncached_input = 0
    cache_read = 0
    reasoning = 0
    completeness: dict[str, int] = {}
    pricing: dict[str, int] = {}
    outcome: dict[str, int] = {}

    for r in rows:
        receipt_count += 1
        request_ids.add(str(getattr(r, "request_id", "")))
        total_cost += int(getattr(r, "calculated_cost_microdollars", 0) or 0)
        total_reserved += int(getattr(r, "reserved_microdollars", 0) or 0)
        legacy_cost += int(getattr(r, "legacy_cost_microdollars", 0) or 0)
        input_tokens += int(getattr(r, "total_input_tokens", 0) or 0)
        output_tokens += int(getattr(r, "total_output_tokens", 0) or 0)
        uncached_input += int(getattr(r, "uncached_input_tokens", 0) or 0)
        cache_read += int(getattr(r, "cache_read_tokens", 0) or 0)
        reasoning += int(getattr(r, "reasoning_output_tokens", 0) or 0)
        completeness[str(getattr(r, "usage_completeness", ""))] = (
            completeness.get(str(getattr(r, "usage_completeness", "")), 0) + 1
        )
        pricing[str(getattr(r, "pricing_completeness", ""))] = (
            pricing.get(str(getattr(r, "pricing_completeness", "")), 0) + 1
        )
        outcome[str(getattr(r, "execution_outcome", ""))] = (
            outcome.get(str(getattr(r, "execution_outcome", "")), 0) + 1
        )

    return SpendAggregate(
        scope={scope.value: scope_value},
        period_start=period_start,
        period_end=period_end,
        receipt_count=receipt_count,
        request_count=len(request_ids - {""}),
        total_cost_microdollars=total_cost,
        total_reserved_microdollars=total_reserved,
        legacy_cost_microdollars=legacy_cost,
        total_input_tokens=input_tokens,
        total_output_tokens=output_tokens,
        total_uncached_input_tokens=uncached_input,
        total_cache_read_tokens=cache_read,
        total_reasoning_output_tokens=reasoning,
        completeness_breakdown=completeness,
        pricing_completeness_breakdown=pricing,
        execution_outcome_breakdown=outcome,
    )

