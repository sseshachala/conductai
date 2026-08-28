from app.runtime.model_router import resolve

ANTHROPIC_MAP = {"cheap": "claude-haiku-4-5-20251001", "balanced": "claude-sonnet-4-6", "smart": "claude-opus-4-7"}
OPENAI_MAP    = {"cheap": "gpt-4.1-mini", "balanced": "gpt-4.1", "smart": "gpt-4.1"}
TIER_MAP = {"anthropic": ANTHROPIC_MAP, "openai": OPENAI_MAP}


def test_resolve_uses_workspace_preferred_provider_and_tier():
    provider, model, reason = resolve("anthropic", TIER_MAP, "balanced")
    assert provider == "anthropic"
    assert model == "claude-sonnet-4-6"
    assert "tier_map[balanced]" in reason


def test_resolve_maps_legacy_preference_names_to_tiers():
    # quality -> smart
    _, model, _ = resolve("anthropic", TIER_MAP, "quality")
    assert model == "claude-opus-4-7"
    # speed / cost -> cheap
    _, model, _ = resolve("openai", TIER_MAP, "speed")
    assert model == "gpt-4.1-mini"
    _, model, _ = resolve("openai", TIER_MAP, "cost")
    assert model == "gpt-4.1-mini"


def test_resolve_honours_explicit_model_over_everything():
    provider, model, reason = resolve("anthropic", TIER_MAP, "balanced", explicit_model="gpt-4.1")
    assert provider == "openai"
    assert model == "gpt-4.1"
    assert reason == "user-pinned model"


def test_resolve_honours_explicit_provider_via_workspace_tier_map():
    provider, model, reason = resolve("anthropic", TIER_MAP, "balanced", explicit_provider="openai")
    assert provider == "openai"
    assert model == "gpt-4.1"
    assert "explicit provider openai" in reason


def test_resolve_falls_back_when_tier_map_missing_the_tier():
    # only balanced defined for openai
    partial = {"openai": {"balanced": "gpt-4.1"}}
    provider, model, reason = resolve("openai", partial, "smart")
    assert provider == "openai"
    assert model == "gpt-4.1-mini"  # provider fallback
    assert "fallback" in reason


def test_resolve_falls_back_when_workspace_has_unknown_provider():
    provider, model, _ = resolve("bogus-provider", TIER_MAP, "balanced")
    # unknown provider is normalised to anthropic default
    assert provider == "anthropic"
    assert model == "claude-sonnet-4-6"
