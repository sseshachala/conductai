"""Session 6E self-checks — Lens streaming usage capture + reader primitives.

Covers the API Lens's conversational surface will consume. The Postgres-
backed drilldown queries land in tests/integration/test_lens_reader_realdb.py
(nightly, RUN_ACCOUNTING_REALDB=1).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.runtime.accounting import (
    AggregateScope,
    CacheSavings,
    SpendAggregate,
    aggregate_from_rows,
    compute_cache_savings,
)
from app.runtime.accounting.contracts import (
    PricingCompleteness,
    UsageCompleteness,
)


# ─── Adapter streaming captures usage ────────────────────────────────────


def test_openai_stream_payload_includes_include_usage():
    """Reviewer #8 follow-up. Lens streaming used to return
    usage_completeness=UNAVAILABLE because the OpenAI SDK never emitted
    the terminal usage chunk. Adapter now opts in unconditionally so
    every stream ends with a usage frame the writer can normalize."""
    import inspect

    from app.runtime.llm_client import OpenAIClient

    src = inspect.getsource(OpenAIClient.stream)
    assert '"stream_options": {"include_usage": True}' in src


def test_anthropic_stream_captures_last_usage_field():
    """Verifies the adapter's stream method exposes ``last_usage`` after
    iteration. The Lens hook reads it via ``getattr(client, 'last_usage', None)``."""
    import inspect

    from app.runtime.llm_client import AnthropicClient

    src = inspect.getsource(AnthropicClient.stream)
    assert "self.last_usage = None" in src
    assert "self.last_usage" in src


def test_anthropic_usage_to_dict_handles_object_form():
    from app.runtime.adapters.anthropic import _usage_to_dict

    class _Usage:
        input_tokens = 100
        output_tokens = 50
        cache_read_input_tokens = 20
        cache_creation_input_tokens = None  # missing

    result = _usage_to_dict(_Usage())
    assert result == {
        "input_tokens": 100,
        "output_tokens": 50,
        "cache_read_input_tokens": 20,
    }


def test_anthropic_usage_to_dict_handles_dict_form():
    from app.runtime.adapters.anthropic import _usage_to_dict

    src = {"input_tokens": 10, "output_tokens": 5}
    assert _usage_to_dict(src) == src
    # Returns a copy, not the same reference.
    assert _usage_to_dict(src) is not src


def test_anthropic_usage_to_dict_extracts_tiered_cache_creation():
    from app.runtime.adapters.anthropic import _usage_to_dict

    class _CacheTiers:
        ephemeral_5m_input_tokens = 200
        ephemeral_1h_input_tokens = 50

    class _Usage:
        input_tokens = 100
        output_tokens = 30
        cache_read_input_tokens = None
        cache_creation_input_tokens = None
        cache_creation = _CacheTiers()

    result = _usage_to_dict(_Usage())
    assert result["cache_creation"] == {
        "ephemeral_5m_input_tokens": 200,
        "ephemeral_1h_input_tokens": 50,
    }


# ─── AccountingReader drilldown contracts (SQL path tested in real-DB file) ─


def test_receipts_for_session_signature_present():
    """The Lens session-drilldown consumer needs this method — pin its
    signature so the API contract doesn't drift silently."""
    import inspect

    from app.runtime.accounting import AccountingReader

    sig = inspect.signature(AccountingReader.receipts_for_session)
    params = list(sig.parameters.keys())
    assert "workspace_id" in params
    assert "hook_session_id" in params
    assert "limit" in params


def test_receipts_for_request_signature_present():
    """Lens per-request drilldown ('why was this budget-blocked?')."""
    import inspect

    from app.runtime.accounting import AccountingReader

    sig = inspect.signature(AccountingReader.receipts_for_request)
    params = list(sig.parameters.keys())
    assert "workspace_id" in params
    assert "request_id" in params


# ─── Cache-savings helper: Lens must not invent this math ───────────────


def _agg(**overrides) -> SpendAggregate:
    """Build a SpendAggregate for the cache-savings tests without hitting the DB."""
    now = datetime.now(timezone.utc)
    base = dict(
        scope={"workspace": "ws"},
        period_start=now,
        period_end=now + timedelta(hours=1),
        receipt_count=1,
        request_count=1,
        total_cost_microdollars=0,
        total_reserved_microdollars=0,
        legacy_cost_microdollars=0,
        total_input_tokens=0,
        total_output_tokens=0,
        total_uncached_input_tokens=0,
        total_cache_read_tokens=0,
        total_reasoning_output_tokens=0,
    )
    base.update(overrides)
    return SpendAggregate(**base)


def test_cache_savings_zero_when_no_cache_reads():
    agg = _agg(total_cache_read_tokens=0, total_uncached_input_tokens=1000)
    r = compute_cache_savings(
        agg,
        uncached_rate_per_1m_usd=Decimal("3.00"),
        cache_read_rate_per_1m_usd=Decimal("0.30"),
    )
    assert r.savings_microdollars == 0


def test_cache_savings_computes_delta_correctly():
    """8000 cache reads at Claude Sonnet rates: uncached_rate=$3/1M,
    cache_read_rate=$0.30/1M. Savings = 8000 × (3.00 - 0.30) / 1M = $0.0216
    = 21_600 microdollars."""
    agg = _agg(total_cache_read_tokens=8000, total_uncached_input_tokens=2000)
    r = compute_cache_savings(
        agg,
        uncached_rate_per_1m_usd=Decimal("3.00"),
        cache_read_rate_per_1m_usd=Decimal("0.30"),
    )
    assert r.savings_microdollars == 21_600


def test_cache_savings_counterfactual_totals_all_input_at_uncached_rate():
    """counterfactual = (cache_read + uncached) × uncached_rate / 1M.
    2000 uncached + 8000 cache_read = 10_000 tokens × $3/1M = $0.030 =
    30_000 μUSD."""
    agg = _agg(total_cache_read_tokens=8000, total_uncached_input_tokens=2000)
    r = compute_cache_savings(
        agg,
        uncached_rate_per_1m_usd=Decimal("3.00"),
        cache_read_rate_per_1m_usd=Decimal("0.30"),
    )
    assert r.counterfactual_cost_microdollars == 30_000


def test_cache_savings_frozen():
    from dataclasses import FrozenInstanceError

    agg = _agg()
    r = compute_cache_savings(
        agg,
        uncached_rate_per_1m_usd=Decimal("3.00"),
        cache_read_rate_per_1m_usd=Decimal("0.30"),
    )
    with pytest.raises(FrozenInstanceError):
        r.savings_microdollars = 999  # type: ignore[misc]
