"""Session 6K self-checks — pins Sudhi's 2 code blockers on 4d4d3402.

The DCO sign-off fix is a git-history change, not code, so it has no
test coverage here.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.runtime.accounting.contracts import PricingCompleteness


# ─── #1 handle_gateway_request non-inference operation path ─────────────


def test_gateway_handler_non_inference_uses_local_operation_var():
    """Reviewer #1 (#2221 review at 4d4d3402): line 289 of
    handle_gateway_request runs when ``operation != "inference"`` — the
    Anthropic token-count path. ``plan`` is not in scope there; using
    ``plan.operation`` raised NameError and broke every non-inference
    request even when shadow accounting was disabled. Fixed to use the
    local ``operation`` variable. Pinned via source-string check so
    a future refactor cannot silently reintroduce the bug."""
    import inspect
    from app.modules.guard import gateway_handler

    src = inspect.getsource(gateway_handler)
    # The non-inference block at line ~286-291 must not reference
    # ``plan.operation`` — plan is out of scope there.
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if 'if operation != "inference":' in line:
            block = "\n".join(lines[i : i + 8])
            assert "plan.operation" not in block, (
                "handle_gateway_request non-inference branch must use the "
                "local `operation` var, not `plan.operation`."
            )
            assert '"operation": operation' in block
            return
    pytest.fail(
        "Could not find the non-inference operation branch — did the "
        "source get restructured?"
    )


def test_execute_v2_success_and_failure_paths_use_plan_operation():
    """The two _execute_v2 attempt-meta writes (success + AllAttemptsFailed)
    correctly reference ``plan.operation`` — plan IS in scope there.
    Distinct from the handle_gateway_request site above."""
    import inspect
    from app.modules.guard import gateway_handler

    src = inspect.getsource(gateway_handler)
    # Exactly two ``"operation": plan.operation`` (the two _execute_v2
    # attempt-meta writes) — plus the fix keeps the handle_gateway_request
    # site at plain ``operation``.
    assert src.count('"operation": plan.operation') == 2
    assert src.count('"operation": operation') == 1


# ─── #2 strict cache-tier pricing without a rate-card tier map ─────────


def test_strict_unknown_tier_marks_incomplete_even_without_card_tier_map():
    """Reviewer #2 (#2221 review at 4d4d3402): prior code skipped tier
    validation entirely when the rate card had no ``cache_write_by_tier``
    map. An unknown tier then took the single-tier default rate and got
    marked PRICED. Now tier validation runs whenever the CALLER supplies
    a tier breakdown — missing card tier data + strict → INCOMPLETE."""
    from app.runtime.accounting.pricing import PricingService

    # Snapshot deliberately has NO cache_write_by_tier map.
    svc = PricingService(
        pricing_snapshot={
            "version": "test-no-tier",
            "providers": {
                "anthropic": {
                    "no-tier-model": {
                        "input": 3.0,
                        "output": 15.0,
                        "cache_read": 0.30,
                        "cache_write": 3.75,  # single-tier scalar only
                    }
                }
            },
        }
    )
    result = svc.price_tokens(
        "anthropic",
        "no-tier-model",
        uncached_input_tokens=0,
        output_tokens=0,
        cache_write_tokens_by_tier={"ephemeral_5m": 1000},
        strict=True,
    )
    assert result.completeness is PricingCompleteness.INCOMPLETE
    # Cost excludes the unpriced tier — becomes a lower bound.
    assert result.microdollars is None or result.microdollars == 0
    assert "tier_ephemeral_5m_unpriced" in result.provenance.get(
        "cache_write_tiers", {}
    )


def test_non_strict_falls_back_to_single_tier_rate_with_provenance():
    """Under strict=False, an unknown tier falls back to the single-tier
    rate — but provenance flags the fallback so telemetry sees it."""
    from app.runtime.accounting.pricing import PricingService

    svc = PricingService(
        pricing_snapshot={
            "version": "test-no-tier",
            "providers": {
                "anthropic": {
                    "no-tier-model": {
                        "input": 3.0,
                        "output": 15.0,
                        "cache_read": 0.30,
                        "cache_write": 3.75,
                    }
                }
            },
        }
    )
    result = svc.price_tokens(
        "anthropic",
        "no-tier-model",
        uncached_input_tokens=0,
        output_tokens=0,
        cache_write_tokens_by_tier={"ephemeral_5m": 1000},
        strict=False,
    )
    # 1000 tokens × $3.75/1M = 3_750 μUSD
    assert result.microdollars == 3_750
    assert "tier_ephemeral_5m_fallback" in result.provenance.get(
        "cache_write_tiers", {}
    )


def test_default_anthropic_pricing_now_includes_tier_rates():
    """Session 6K also populated ``cache_write_by_tier`` on Anthropic
    defaults so live traffic gets tier-accurate pricing without ops
    having to supply an override."""
    from app.runtime.accounting.pricing import PricingService

    svc = PricingService()  # default snapshot
    card = svc.get_rate_card("anthropic", "claude-sonnet-4-6", strict=True)
    tiers = card.cache_write_by_tier_per_1m_usd
    assert tiers.get("ephemeral_5m") == Decimal("3.75")
    assert tiers.get("ephemeral_1h") == Decimal("6.00")


def test_default_pricing_prices_ephemeral_1h_at_correct_rate():
    """Live path proof: 1000 ephemeral_1h tokens at claude-sonnet-4-6 =
    $6.00/1M = 6_000 μUSD (not $3.75/1M = 3_750, which is the 5m rate)."""
    from app.runtime.accounting.pricing import PricingService

    svc = PricingService()
    result = svc.price_tokens(
        "anthropic",
        "claude-sonnet-4-6",
        uncached_input_tokens=0,
        output_tokens=0,
        cache_write_tokens_by_tier={"ephemeral_1h": 1000},
        strict=True,
    )
    assert result.microdollars == 6_000
    assert result.completeness is PricingCompleteness.PRICED
