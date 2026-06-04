from app.core.config import settings
from app.runtime.pricing import freeze_pricing_snapshot, get_model_rates


def test_default_rates_lookup():
    snapshot = freeze_pricing_snapshot()
    rates, version = get_model_rates("anthropic", "claude-sonnet-4-6", snapshot)

    assert version
    assert rates["input"] == 3.0
    assert rates["output"] == 15.0
    assert rates["cache_read"] == 0.3
    assert rates["cache_write"] == 3.75


def test_override_rates_and_version_applied():
    prev_json = settings.pricing_overrides_json
    prev_ver = settings.pricing_registry_version
    try:
        settings.pricing_registry_version = "base-version"
        settings.pricing_overrides_json = (
            '{"version":"2026-07-01","providers":{"openai":{"gpt-4.1-mini":{"input":0.5,"output":1.7}}}}'
        )

        snapshot = freeze_pricing_snapshot()
        rates, version = get_model_rates("openai", "gpt-4.1-mini", snapshot)

        assert version == "2026-07-01"
        assert rates["input"] == 0.5
        assert rates["output"] == 1.7
    finally:
        settings.pricing_overrides_json = prev_json
        settings.pricing_registry_version = prev_ver


def test_invalid_override_json_falls_back_to_defaults():
    prev_json = settings.pricing_overrides_json
    try:
        settings.pricing_overrides_json = "{not-json}"
        snapshot = freeze_pricing_snapshot()
        rates, _ = get_model_rates("openai", "gpt-4.1-mini", snapshot)
        assert rates["input"] == 0.4
        assert rates["output"] == 1.6
    finally:
        settings.pricing_overrides_json = prev_json


def test_snapshot_freezes_rates_even_if_settings_change_later():
    prev_json = settings.pricing_overrides_json
    prev_ver = settings.pricing_registry_version
    try:
        settings.pricing_registry_version = "v1"
        settings.pricing_overrides_json = (
            '{"version":"v1","providers":{"openai":{"gpt-4.1-mini":{"input":0.4,"output":1.6}}}}'
        )
        snap_v1 = freeze_pricing_snapshot()

        settings.pricing_registry_version = "v2"
        settings.pricing_overrides_json = (
            '{"version":"v2","providers":{"openai":{"gpt-4.1-mini":{"input":0.9,"output":1.9}}}}'
        )

        rates_v1, ver_v1 = get_model_rates("openai", "gpt-4.1-mini", snap_v1)
        rates_latest, ver_latest = get_model_rates("openai", "gpt-4.1-mini")

        assert ver_v1 == "v1"
        assert rates_v1["input"] == 0.4
        assert ver_latest == "v2"
        assert rates_latest["input"] == 0.9
    finally:
        settings.pricing_overrides_json = prev_json
        settings.pricing_registry_version = prev_ver
