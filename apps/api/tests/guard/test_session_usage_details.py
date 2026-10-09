from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.guard.routers.events import HookEvent, SessionUsageReport
from app.modules.guard.session_usage import usage_evidence
from app.runtime.accounting.pricing import PricingService


def report(**kw):
    return SessionUsageReport(workspace_id=uuid4(), hook_session_id=uuid4(), snapshot_id=uuid4(),
                              observed_at=datetime.now(timezone.utc), **kw)


def part(**kw):
    return {"uncached_input_tokens": 100, "cache_read_tokens": 50,
            "cache_write_tokens": 0, "output_tokens": 20,
            "model": "test-model", "provider": "test", **kw}


@pytest.fixture(autouse=True)
def pricing(monkeypatch):
    service = PricingService({"version": "fixture-v1", "providers": {"test": {"test-model": {
        "input": 2, "output": 10, "cache_read": 0.5, "cache_write": 3,
    }}}})
    monkeypatch.setattr("app.modules.guard.session_usage.default_pricing_service", lambda: service)


def test_estimate_preserves_categories_without_reasoning_double_charge():
    result = usage_evidence(report(input_tokens=150, output_tokens=20,
                                   usage=[part(reasoning_output_tokens=10)]))
    assert result["estimated_microdollars"] == 425
    assert result["pricing_version"] == "fixture-v1"
    assert result["reconciliation"] == "unreconciled"
    assert result["budget_eligible"] is False


@pytest.mark.parametrize("override", [{"provider": None}, {"model": "unknown"}])
def test_missing_pricing_is_not_zero(override):
    result = usage_evidence(report(input_tokens=150, output_tokens=20, usage=[part(**override)]))
    assert result["estimated_microdollars"] is None
    assert result["cost_status"] == "unpriced"


@pytest.mark.parametrize("override", [{"uncached_input_tokens": True}, {"cache_read_tokens": -1},
                                       {"reasoning_output_tokens": 21}, {"estimated_microdollars": 1}])
def test_invalid_or_fabricated_metadata_rejected(override):
    with pytest.raises(ValidationError):
        report(input_tokens=150, output_tokens=20, usage=[part(**override)])


def test_slices_must_equal_totals():
    with pytest.raises(ValidationError):
        report(input_tokens=151, output_tokens=20, usage=[part()])


def test_generic_hook_cannot_forge_server_usage_evidence():
    event = HookEvent(workspace_id=str(uuid4()), ai_tool="codex", tool_call="session_usage", decision="audited",
                      _session_usage={"cost_status": "estimated"})
    assert event._session_usage is None


def test_legacy_totals_remain_unpriced():
    result = usage_evidence(report(input_tokens=150, output_tokens=20))
    assert result["estimated_microdollars"] is None
    assert result["slices"] == []
