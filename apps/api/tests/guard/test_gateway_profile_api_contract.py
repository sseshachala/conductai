from app.modules.guard.gateway_config import GatewayProfile, profile_from_legacy


def test_gateway_profile_round_trip_keeps_advanced_settings():
    profile = GatewayProfile(
        name="primary",
        provider="openai",
        protocol="openai_compatible",
        deployments=[{"alias": "balanced", "model": "gpt-4.1", "weight": 2}],
        reliability={"timeout_seconds": 45, "max_retries": 2},
        provider_options={"api_version": "2025-01-01"},
    )

    restored = GatewayProfile.model_validate(profile.model_dump())
    assert restored.deployments[0].model == "gpt-4.1"
    assert restored.reliability.max_retries == 2
    assert restored.provider_options["api_version"] == "2025-01-01"


def test_legacy_profile_does_not_copy_provider_secret():
    profile = profile_from_legacy(
        proxy_config={"LLM_UPSTREAM": "https://gateway.test", "LLM_UPSTREAM_API_KEY": "secret"}
    )

    assert profile.upstream_url == "https://gateway.test"
    assert "secret" not in profile.model_dump_json()
