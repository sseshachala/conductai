from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

import pytest
from pydantic import ValidationError

from app.modules.guard.discovery_inventory import agent_view, clean_evidence, summarize
from app.modules.guard.routers.discovery import ScanIn

NOW = datetime.now(timezone.utc)


def row(**overrides):
    values = dict(id=uuid.uuid4(), framework="codex", source="inventory", device_id=uuid.uuid4(),
                  installation_id="a" * 64, detection="installed", evidence={"hooks_configured": True, "gateway_configured": True},
                  last_seen_at=NOW, first_seen_at=NOW, hook_observed_at=None, hook_event_id=None)
    return SimpleNamespace(**{**values, **overrides})


def test_configuration_is_not_observation():
    result = agent_view(row(), NOW)
    assert result["hooks_status"] == "configured"
    assert result["gateway_status"] == "configured"
    assert result["under_guard"] is False
    assert result["proxy_routed"] is False


def test_only_recent_linked_hook_is_observed():
    assert agent_view(row(hook_observed_at=NOW), NOW)["hooks_status"] == "configured"
    result = agent_view(row(hook_observed_at=NOW, hook_event_id=uuid.uuid4()), NOW)
    assert result["hooks_status"] == "observed"
    assert summarize([result])["recent_hook_evidence"] == 1
    assert "coverage_pct" not in summarize([result])


@pytest.mark.parametrize("delta", [timedelta(days=-2), timedelta(minutes=1)])
def test_stale_or_future_timestamps_do_not_prove_current_state(delta):
    result = agent_view(row(last_seen_at=NOW + delta, hook_observed_at=NOW + delta, hook_event_id=uuid.uuid4()), NOW)
    assert result["freshness"] == "stale"
    assert result["hooks_status"] == result["gateway_status"] == "unverified"


def test_legacy_flags_and_forged_evidence_are_not_authority():
    result = agent_view(row(device_id=None, under_guard=True, proxy_routed=True, hook_event_id=uuid.uuid4(), hook_observed_at=NOW), NOW)
    assert result["detection"] == "legacy_unverified"
    assert result["hooks_status"] == "unverified"
    assert not result["under_guard"]
    assert clean_evidence({"signals": ["tool_installation", "secret", {}], "hooks_configured": "yes", "cmdline": "secret", "hook_event_id": "forged"}) == {"signals": ["tool_installation"]}


def test_v2_requires_identity_and_rejects_duplicate_installations():
    with pytest.raises(ValidationError):
        ScanIn(schema_version=2, agents=[])
    agent = {"framework": "codex", "installation_id": "a" * 64, "detection": "installed"}
    with pytest.raises(ValidationError):
        ScanIn(schema_version=2, device_id=uuid.uuid4(), agents=[agent, agent])
    assert ScanIn(schema_version=2, device_id=uuid.uuid4(), agents=[agent]).schema_version == 2


def test_scan_cannot_supply_observation_fields():
    scan = ScanIn(schema_version=2, device_id=uuid.uuid4(), agents=[{
        "framework": "codex", "installation_id": "a" * 64, "detection": "installed",
        "hook_event_id": str(uuid.uuid4()), "under_guard": True, "hook_observed_at": NOW.isoformat(),
    }])
    assert "hook_event_id" not in scan.agents[0].model_dump()
    assert "under_guard" not in scan.agents[0].model_dump()
