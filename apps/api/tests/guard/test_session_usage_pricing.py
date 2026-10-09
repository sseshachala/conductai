"""Pricing of client-reported usage: provider inference, LiteLLM fallback, cache-write tier, coverage."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.modules.guard.routers.events import SessionUsageReport
from app.modules.guard.session_usage import build_evidence, evidence_cost_usd, usage_evidence
from app.runtime.accounting.pricing import PricingService
from app.runtime.provider_inference import infer_provider_from_model

LITELLM = {
    # per-token costs as in litellm.model_cost
    "claude-opus-5-5": {"litellm_provider": "anthropic", "input_cost_per_token": 4e-06,
                        "output_cost_per_token": 2e-05, "cache_read_input_token_cost": 2e-07,
                        "cache_creation_input_token_cost": 5e-06,
                        "cache_creation_input_token_cost_above_1hr": 8e-06},
    "gpt-6.1-sol": {"litellm_provider": "openai", "input_cost_per_token": 2e-06,
                    "output_cost_per_token": 1e-05, "cache_read_input_token_cost": 1e-07},
    "claude-sonnet-4-6": {"litellm_provider": "anthropic", "input_cost_per_token": 99e-06,
                          "output_cost_per_token": 99e-06},
    "no-cache-write": {"litellm_provider": "openai", "input_cost_per_token": 1e-06,
                       "output_cost_per_token": 1e-06, "cache_read_input_token_cost": 1e-07},
}
OUR_TABLE = {"version": "fixture-v1", "providers": {"anthropic": {"claude-sonnet-4-6": {
    "input": 3.0, "output": 15.0, "cache_read": 0.3, "cache_write": 3.75,
    "cache_write_by_tier": {"ephemeral_5m": 3.75, "ephemeral_1h": 6.0}}}}}


@pytest.fixture(autouse=True)
def pricing(monkeypatch):
    service = PricingService(OUR_TABLE)
    monkeypatch.setattr("app.modules.guard.session_usage.default_pricing_service", lambda: service)
    monkeypatch.setattr("app.runtime.litellm_rates._cost_map", lambda: LITELLM)
    monkeypatch.setattr("app.runtime.accounting.pricing.litellm_version", lambda: "9.9.9")
    return service


def slice_(**kw):
    return {"model": "claude-opus-5-5", "provider": None, "uncached_input_tokens": 1000,
            "cache_read_tokens": 0, "cache_write_tokens": 0, "output_tokens": 100, **kw}


def evidence(*parts, coverage=None):
    return build_evidence(list(parts), "2026-10-01T00:00:00+00:00", coverage)


@pytest.mark.parametrize("model,provider", [
    ("claude-opus-5-5", "anthropic"), ("gpt-6.1-sol", "openai"), ("o3-mini", "openai"),
    ("o4", "openai"), ("codex-mini-latest", "openai"), ("gemini-2.5-pro", "google"),
    ("mystery-model", None), ("", None), (None, None),
])
def test_provider_inference(model, provider):
    assert infer_provider_from_model(model) == provider


def test_null_provider_is_inferred_and_priced():
    result = evidence(slice_())
    assert result["slices"][0]["provider_inferred"] == "anthropic"
    assert result["slices"][0]["provider"] is None
    assert result["estimated_microdollars"] == 1000 * 4 + 100 * 20  # per-1M rates in microdollars/token


def test_unknown_prefix_stays_unpriced():
    result = evidence(slice_(model="mystery-model"))
    assert result["cost_status"] == "unpriced"
    assert result["slices"][0]["unpriced_reason"] == "missing_model_or_provider"
    assert evidence_cost_usd(result) is None


def test_litellm_prices_unlisted_model_and_marks_version():
    result = evidence(slice_(model="gpt-6.1-sol", provider="openai", cache_read_tokens=500))
    assert result["estimated_microdollars"] == 1000 * 2 + 500 * 0.1 + 100 * 10
    assert result["slices"][0]["pricing_source"] == "litellm"
    assert result["pricing_version"] == "fixture-v1+litellm-9.9.9"


def test_our_table_wins_over_litellm(pricing):
    result = evidence(slice_(model="claude-sonnet-4-6"))
    assert result["estimated_microdollars"] == 1000 * 3 + 100 * 15
    assert "pricing_source" not in result["slices"][0]
    assert result["pricing_version"] == "fixture-v1"
    assert pricing.rates_for("anthropic", "claude-sonnet-4-6")[0]["input"] == 3.0


def test_litellm_requires_matching_provider():
    assert evidence(slice_(model="gpt-6.1-sol", provider="anthropic"))["cost_status"] == "unpriced"


def test_cache_write_assumes_five_minute_tier_on_litellm_rates():
    result = evidence(slice_(cache_write_tokens=1000, uncached_input_tokens=0))
    part = result["slices"][0]
    assert part["cache_write_tier_assumed"] == "5m"
    assert result["cost_status"] == "estimated"
    assert result["estimated_microdollars"] == 1000 * 5 + 100 * 20  # not the 1h rate of 8


def test_cache_write_uses_five_minute_rate_of_our_table():
    result = evidence(slice_(model="claude-sonnet-4-6", cache_write_tokens=1000, uncached_input_tokens=0))
    assert result["estimated_microdollars"] == 1000 * 3.75 + 100 * 15
    assert result["slices"][0]["cache_write_tier_assumed"] == "5m"


def test_cache_write_unpriced_only_when_no_rate_exists():
    part = slice_(model="no-cache-write", provider="openai", cache_write_tokens=10)
    result = evidence(part)
    assert result["slices"][0]["unpriced_reason"] == "cache_write_tier_unavailable"
    assert result["cost_status"] == "unpriced"


class FakeCoverage:
    def classify(self, part):
        if part.get("provider_response_id"):
            return ("response_or_request_id_match", "gateway")
        return ("session_has_gateway_receipts", "gateway_session")


def test_gateway_covered_slices_keep_tokens_but_are_not_counted():
    result = evidence(slice_(provider_response_id="msg_abc"), slice_(model="gpt-6.1-sol", provider="openai"),
                      coverage=FakeCoverage())
    first, second = result["slices"]
    assert (first["covered_by"], first["estimated_microdollars"]) == ("gateway", 0)
    assert first["uncached_input_tokens"] == 1000
    assert first["gateway_priced_microdollars"] == 1000 * 4 + 100 * 20
    assert first["coverage_rule"] == "response_or_request_id_match"
    assert second["covered_by"] == "gateway_session"
    assert result["cost_status"] == "estimated"
    assert result["estimated_microdollars"] == 0
    assert evidence_cost_usd(result) == 0


def test_only_uncovered_slices_sum():
    class OnlyIds(FakeCoverage):
        def classify(self, part):
            return super().classify(part) if part.get("provider_response_id") else None
    result = evidence(slice_(provider_response_id="msg_abc"), slice_(model="gpt-6.1-sol", provider="openai"),
                      slice_(model="mystery-model"), coverage=OnlyIds())
    assert result["cost_status"] == "partial"
    assert result["estimated_microdollars"] == 1000 * 2 + 100 * 10
    assert evidence_cost_usd(result) == pytest.approx(0.003)


def test_usage_evidence_from_report_and_priced_cost():
    report = SessionUsageReport(workspace_id=uuid4(), hook_session_id=uuid4(), snapshot_id=uuid4(),
                                observed_at=datetime.now(timezone.utc), input_tokens=1000, output_tokens=100,
                                usage=[slice_()])
    result = usage_evidence(report)
    assert result["cost_status"] == "estimated" and result["budget_eligible"] is False
    assert evidence_cost_usd(result) == pytest.approx(0.006)


def test_rebuilding_from_stored_evidence_is_deterministic():
    first = evidence(slice_(provider_response_id="msg_abc"), slice_(model="gpt-6.1-sol", provider="openai"))
    again = build_evidence(first["slices"], first["observed_at"])
    assert again["slices"] == first["slices"] and again["estimated_microdollars"] == first["estimated_microdollars"]


@pytest.fixture
def registry(monkeypatch):
    """Real default registry with an empty LiteLLM table: any price must come from our table."""
    service = PricingService()
    monkeypatch.setattr("app.modules.guard.session_usage.default_pricing_service", lambda: service)
    monkeypatch.setattr("app.runtime.litellm_rates._cost_map", lambda: {})


def test_opus_5_5_priced_from_our_registry_with_tiers(registry):
    result = evidence(slice_(cache_read_tokens=1000, cache_write_tokens=1000))
    part = result["slices"][0]
    assert "pricing_source" not in part and "+litellm" not in result["pricing_version"]
    assert part["cache_write_tier_assumed"] == "5m"
    # input 4 + cache_read 0.20 + cache_write(5m) 5 + output 20, per 1M tokens
    assert result["estimated_microdollars"] == 1000 * 4 + 1000 * 0.2 + 1000 * 5 + 100 * 20


def test_gpt_6_1_sol_priced_from_our_registry(registry):
    result = evidence(slice_(model="gpt-6.1-sol", provider="openai", cache_read_tokens=500, cache_write_tokens=100))
    assert "pricing_source" not in result["slices"][0] and "+litellm" not in result["pricing_version"]
    assert result["estimated_microdollars"] == 1000 * 2 + 500 * 0.1 + 100 * 2.5 + 100 * 10
