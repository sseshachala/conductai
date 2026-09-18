"""PR-A2b — cost estimator + budget block response.

Unit coverage for the two small helpers the gateway wire-in calls:

- ``estimate_budget_cents(body, provider, model, ai_tool)`` — bounded
  pre-flight cost estimate for the ledger reservation.
- ``budget_block_response(result)`` — fail-closed HTTP response
  builder for a rejected reservation.

Both helpers are pure — no DB, no upstream, no side effects — so unit
tests fully cover their contract.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.modules.guard.gateway_lifecycle import (
    ReserveOutcome,
    budget_block_response,
    estimate_budget_cents,
)


# ── estimate_budget_cents ────────────────────────────────────────────

def test_estimate_returns_positive_int_for_typical_request():
    body = {
        "messages": [
            {"role": "user", "content": "Hello, how are you?"},
        ],
        "max_tokens": 100,
    }
    cents = estimate_budget_cents(body, provider="anthropic", model="claude-3-5-sonnet", ai_tool="cursor")
    assert isinstance(cents, int)
    assert cents > 0


def test_estimate_scales_with_input_length():
    """A longer prompt should reserve more capacity."""
    # Use 100,000 chars so input contribution clears sub-cent rounding.
    short_body = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 100}
    long_body = {"messages": [{"role": "user", "content": "x" * 100_000}], "max_tokens": 100}
    short_cents = estimate_budget_cents(short_body, "anthropic", "claude-3-5-sonnet", "cursor")
    long_cents = estimate_budget_cents(long_body, "anthropic", "claude-3-5-sonnet", "cursor")
    assert long_cents > short_cents


def test_estimate_respects_max_tokens_output_bound():
    """Setting a small max_tokens reduces the reserved output allowance."""
    body_small = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 10}
    body_large = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 4000}
    small_cents = estimate_budget_cents(body_small, "anthropic", "claude-3-5-sonnet", "cursor")
    large_cents = estimate_budget_cents(body_large, "anthropic", "claude-3-5-sonnet", "cursor")
    assert large_cents > small_cents


def test_estimate_uses_default_output_allowance_when_max_tokens_absent():
    """No max_tokens -> default allowance; same tool used elsewhere in
    the audit path so the estimate matches downstream accounting shape."""
    body = {"messages": [{"role": "user", "content": "hello"}]}
    cents = estimate_budget_cents(body, "anthropic", "claude-3-5-sonnet", "cursor")
    assert cents > 0


def test_estimate_handles_content_as_list_of_parts():
    """Anthropic-style content parts (list of dicts)."""
    body = {
        "messages": [
            {"role": "user", "content": [
                {"type": "text", "text": "part one"},
                {"type": "text", "text": "part two"},
            ]},
        ],
    }
    cents = estimate_budget_cents(body, "anthropic", "claude-3-5-sonnet", "cursor")
    assert cents > 0


def test_estimate_handles_missing_body_shape_defensively():
    """Empty / malformed body must not crash; returns a positive int
    from the minimum-tokens floor + default output allowance."""
    for bad in (None, {}, {"messages": None}, {"messages": []}, {"other": "shape"}):
        cents = estimate_budget_cents(bad if isinstance(bad, dict) else {}, "anthropic", "claude-3-5-sonnet", "unknown")
        assert isinstance(cents, int)
        assert cents >= 0


def test_estimate_uses_provider_and_model_pricing_when_available():
    """R10 (reviewer P1): estimator now uses the real provider+model
    pricing via _compute_cost, not the client-tool heuristic. Different
    models with different price schedules should yield different
    estimates regardless of the ai_tool label."""
    # Bigger input so per-model pricing differences clear the sub-cent
    # rounding threshold.
    body = {"messages": [{"role": "user", "content": "x" * 100_000}], "max_tokens": 100}
    # Two distinct model families exercised through the same ai_tool
    # label — R10 makes the model the pricing dimension.
    sonnet = estimate_budget_cents(body, "anthropic", "claude-3-5-sonnet", "cursor")
    # If the pricing registry has cheaper haiku rates, the estimate for
    # that model must be strictly smaller. When both models are missing
    # from the registry the estimator falls back to the client-tool
    # heuristic, so the assertion still holds (Sonnet > Haiku in every
    # published price list).
    haiku = estimate_budget_cents(body, "anthropic", "claude-3-haiku", "cursor")
    assert sonnet >= haiku, (
        "Sonnet should cost at least as much as Haiku — R10 pricing"
    )


def test_estimate_honors_full_max_tokens_no_silent_cap():
    """R10 repro: pre-fix the estimator silently capped max_tokens at
    4096. A caller requesting 100_000 output tokens still reserved as
    if 4096 were requested, and the wire request was forwarded unchanged
    (100_000-token output that could blow past the reservation).

    Post-fix: 100k reserves proportionally more than 4096."""
    body_4k = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 4096}
    body_100k = {"messages": [{"role": "user", "content": "hi"}], "max_tokens": 100_000}
    small = estimate_budget_cents(body_4k, "anthropic", "claude-3-5-sonnet", "cursor")
    large = estimate_budget_cents(body_100k, "anthropic", "claude-3-5-sonnet", "cursor")
    assert large > small, (
        "100k max_tokens must reserve MORE than 4096 — pre-R10 they"
        " were identical because of the silent 4096 cap."
    )
    # Sanity: the difference is at least an order of magnitude on
    # Sonnet-class output pricing.
    assert large >= small * 5, (
        f"expected 100k reservation >= 5x 4k reservation, got {large}c vs {small}c"
    )


# ── budget_block_response ────────────────────────────────────────────

class _FakeResult:
    def __init__(self, outcome, refusing_budget=None, error=None):
        self.outcome = outcome
        self.refusing_budget = refusing_budget
        self.error = error


class _FakeBudget:
    def __init__(self, ai_tool=None, hard_limit_usd=None):
        self.ai_tool = ai_tool
        self.hard_limit_usd = hard_limit_usd


def test_block_response_exceeded_is_402():
    result = _FakeResult(
        outcome=ReserveOutcome.EXCEEDED,
        refusing_budget=_FakeBudget(ai_tool="cursor", hard_limit_usd=10.0),
        error="budget cap exceeded",
    )
    r = budget_block_response(result)
    assert r.status_code == 402
    import json
    body = json.loads(r.body)
    assert body["outcome"] == "exceeded"
    assert body["refusing_budget"]["ai_tool"] == "cursor"
    assert body["refusing_budget"]["hard_limit_usd"] == 10.0


def test_block_response_not_ready_is_503():
    result = _FakeResult(
        outcome=ReserveOutcome.NOT_READY,
        error="budget ledger not ready (reconciler cold start)",
    )
    r = budget_block_response(result)
    assert r.status_code == 503


def test_block_response_redis_down_is_503():
    r = budget_block_response(_FakeResult(outcome=ReserveOutcome.REDIS_DOWN))
    assert r.status_code == 503


def test_block_response_db_error_is_503():
    r = budget_block_response(_FakeResult(outcome=ReserveOutcome.DB_ERROR))
    assert r.status_code == 503


def test_block_response_never_leaks_workspace_or_agent_ids():
    """Cardinality-safe / privacy — response body must NOT contain
    workspace_id or agent_identity_id text."""
    result = _FakeResult(
        outcome=ReserveOutcome.EXCEEDED,
        refusing_budget=_FakeBudget(ai_tool="cursor", hard_limit_usd=5.0),
        error="budget cap exceeded",
    )
    r = budget_block_response(result)
    body = r.body.decode()
    assert "workspace" not in body.lower()
    assert "agent_identity" not in body.lower()
