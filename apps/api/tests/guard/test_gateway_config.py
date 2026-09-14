import pytest
from pydantic import ValidationError

from app.modules.guard.gateway_config import GatewayProfile, profile_from_legacy


def test_profile_normalizes_provider_and_upstream_url():
    profile = GatewayProfile(
        name="Primary",
        provider=" Anthropic ",
        protocol="anthropic",
        upstream_url="https://api.example.test/",
    )

    assert profile.provider == "anthropic"
    assert profile.upstream_url == "https://api.example.test"
    assert profile.streaming.no_retry_after_first_byte is True


def test_profile_rejects_unknown_fields_and_invalid_upstream():
    with pytest.raises(ValidationError):
        GatewayProfile(
            name="Primary",
            provider="anthropic",
            protocol="anthropic",
            upstream_url="ftp://api.example.test",
        )

    with pytest.raises(ValidationError):
        GatewayProfile(
            name="Primary",
            provider="anthropic",
            protocol="anthropic",
            unexpected="value",
        )


def test_legacy_projection_combines_proxy_and_model_settings_without_secret():
    profile = profile_from_legacy(
        proxy_config={
            "LLM_UPSTREAM": "https://litellm.example.test/v1/",
            "credential_ref": "vault://providers/anthropic",
            "LLM_UPSTREAM_API_KEY": "must-not-be-copied",
        },
        llm_primitives={
            "preferred_provider": "openai",
            "tier_map": {
                "openai": {
                    "cheap": "gpt-mini",
                    "balanced": "gpt-standard",
                }
            },
        },
        environment_id="env-1",
    )

    assert profile.provider == "openai"
    assert profile.protocol == "openai_compatible"
    assert profile.upstream_url == "https://litellm.example.test/v1"
    assert profile.credential_ref == "vault://providers/anthropic"
    assert [(d.alias, d.model) for d in profile.deployments] == [
        ("cheap", "gpt-mini"),
        ("balanced", "gpt-standard"),
    ]
    assert "LLM_UPSTREAM_API_KEY" not in profile.model_dump()


def test_legacy_projection_defaults_to_anthropic():
    profile = profile_from_legacy()

    assert profile.provider == "anthropic"
    assert profile.protocol == "anthropic"
    assert profile.deployments == []


def test_litellm_options_are_validated_and_secret_free():
    profile = GatewayProfile(
        name="litellm",
        provider="openai",
        protocol="openai_compatible",
        litellm={
            "api_base": "https://litellm.internal/v1/",
            "custom_llm_provider": "openai",
            "drop_params": True,
            "request_timeout_seconds": 45,
            "num_retries": 2,
        },
    )
    assert profile.litellm.api_base == "https://litellm.internal/v1"
    assert "api_key" not in profile.model_dump_json()


def test_litellm_options_reject_invalid_base_and_unknown_fields():
    with pytest.raises(ValidationError):
        GatewayProfile(
            name="bad",
            provider="openai",
            protocol="openai_compatible",
            litellm={"api_base": "file:///tmp/provider"},
        )
    with pytest.raises(ValidationError):
        GatewayProfile(
            name="bad",
            provider="openai",
            protocol="openai_compatible",
            litellm={"api_key": "sk-secret"},
        )
