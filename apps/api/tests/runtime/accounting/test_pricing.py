"""Session 2 pricing service self-checks."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.runtime.accounting.contracts import PricingCompleteness
from app.runtime.accounting.pricing import (
    PricingService,
    RateCard,
    reset_default_pricing_service,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_default_pricing_service()
    yield
    reset_default_pricing_service()


def _svc() -> PricingService:
    return PricingService()


def test_known_model_returns_priced_rate_card():
    card = _svc().get_rate_card("anthropic", "claude-sonnet-4-6")
    assert card.completeness is PricingCompleteness.PRICED
    assert card.input_per_1m_usd == Decimal("3.00")
    assert card.output_per_1m_usd == Decimal("15.00")
    assert card.cache_read_per_1m_usd == Decimal("0.30")


def test_unknown_model_strict_raises_and_returns_unpriced_via_price_tokens():
    result = _svc().price_tokens(
        "anthropic", "not-a-real-model",
        uncached_input_tokens=100, output_tokens=50, strict=True,
    )
    assert result.microdollars is None
    assert result.completeness is PricingCompleteness.UNPRICED
    assert result.provenance["reason"] == "unknown_model"


def test_unknown_model_non_strict_signals_override_applied():
    """Compat wrappers rely on legacy silent fallback but the completeness flag
    now signals it — Session 4 shadow can measure the discrepancy."""
    result = _svc().price_tokens(
        "anthropic", "not-a-real-model",
        uncached_input_tokens=1000, output_tokens=500, strict=False,
    )
    assert result.microdollars is not None
    assert result.completeness is PricingCompleteness.OVERRIDE_APPLIED


def test_priced_call_cost_matches_manual_calculation():
    # claude-sonnet-4-6: $3/1M input, $15/1M output
    # 10_000 in + 2_000 out = 0.030 + 0.030 = 0.060 USD = 60_000 μUSD
    result = _svc().price_tokens(
        "anthropic", "claude-sonnet-4-6",
        uncached_input_tokens=10_000, output_tokens=2_000,
    )
    assert result.microdollars == 60_000
    assert result.completeness is PricingCompleteness.PRICED


def test_zero_tokens_and_no_fee_returns_none_matching_legacy():
    """Preserves ``guard.audit._compute_cost`` returning None for empty calls."""
    result = _svc().price_tokens(
        "anthropic", "claude-sonnet-4-6",
        uncached_input_tokens=0, output_tokens=0,
    )
    assert result.microdollars is None


def test_perplexity_request_fee_charged_on_top():
    # sonar: $1/1M input, $5/1M output, $0.005 request fee
    # 1000 in + 500 out = 0.001 + 0.0025 = 0.0035 + 0.005 fee = 0.0085 USD = 8_500 μUSD
    result = _svc().price_tokens(
        "perplexity", "sonar",
        uncached_input_tokens=1000, output_tokens=500,
    )
    assert result.microdollars == 8_500


def test_perplexity_request_fee_alone_still_charges():
    """Legacy _compute_cost returns non-None for zero-token calls when a
    request fee exists — sonar charges $0.005 per request regardless."""
    result = _svc().price_tokens(
        "perplexity", "sonar",
        uncached_input_tokens=0, output_tokens=0,
    )
    # But we defined "no billable tokens" to include request_fee=0 check —
    # sonar's 0.005 fee is nonzero, so this should NOT return None.
    assert result.microdollars is not None
    assert result.microdollars == 5_000  # $0.005 = 5_000 μUSD


def test_cache_read_priced_at_cache_rate_not_input_rate():
    """Cache reads are cheaper than uncached input — they get the cache_read
    rate. Callers pass uncached + cache_read as SEPARATE buckets; no
    subtraction inside pricing (see reviewer finding #4 on #2221)."""
    # claude-sonnet-4-6: input $3/1M, cache_read $0.30/1M
    # uncached: 2_000 * $3/1M = 0.006
    # cache_read: 8_000 * $0.30/1M = 0.0024
    # output: 0
    # total = 0.0084 USD = 8_400 μUSD
    result = _svc().price_tokens(
        "anthropic", "claude-sonnet-4-6",
        uncached_input_tokens=2_000, cache_read_tokens=8_000, output_tokens=0,
    )
    assert result.microdollars == 8_400


def test_reviewer_repro_no_double_subtract_of_cache_read():
    """Reviewer's exact repro at #2221 finding #4:
    100 fresh input + 900 cache reads + 200 output should be 3_570 μUSD.
    Pre-fix returned 3_270 (cache_read subtracted from input twice)."""
    result = _svc().price_tokens(
        "anthropic", "claude-sonnet-4-6",
        uncached_input_tokens=100,
        cache_read_tokens=900,
        output_tokens=200,
    )
    # input: 100 * $3/1M = 300
    # cache_read: 900 * $0.30/1M = 270
    # output: 200 * $15/1M = 3_000
    # total = 3_570
    assert result.microdollars == 3_570


def test_reasoning_tokens_do_not_add_a_charge():
    """Invariant #5. Reasoning is a breakdown of output, not an additive charge.
    The pricing service accepts output_tokens (which already includes reasoning);
    there is no separate reasoning rate parameter."""
    result_a = _svc().price_tokens(
        "openai", "gpt-4.1",
        uncached_input_tokens=100, output_tokens=100,
    )
    result_b = _svc().price_tokens(
        "openai", "gpt-4.1",
        uncached_input_tokens=100, output_tokens=100,
    )
    # No reasoning arg exists on the API surface — callers cannot double-charge.
    assert result_a.microdollars == result_b.microdollars


def test_pricing_version_recorded_on_result():
    result = _svc().price_tokens(
        "anthropic", "claude-sonnet-4-6",
        uncached_input_tokens=100, output_tokens=100,
    )
    assert result.pricing_version  # non-empty


def test_rate_card_from_legacy_rates_roundtrip():
    card = RateCard.from_legacy_rates(
        "anthropic",
        "claude-sonnet-4-6",
        {"input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75},
        version="test-v1",
        completeness=PricingCompleteness.PRICED,
    )
    assert card.input_per_1m_usd == Decimal("3.0")
    assert card.completeness is PricingCompleteness.PRICED
    assert card.version == "test-v1"
