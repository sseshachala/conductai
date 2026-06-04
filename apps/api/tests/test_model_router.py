from app.runtime.model_router import resolve


def test_resolve_returns_provider_model_and_reason_for_known_slug():
    provider, model, reason = resolve("pr_reviewer", "balanced")

    assert provider == "anthropic"
    assert model == "claude-sonnet-4-6"
    assert reason == "balanced model for code review"


def test_resolve_uses_openai_for_cost_sensitive_triage():
    provider, model, reason = resolve("issue_triage", "cost")

    assert provider == "openai"
    assert model == "gpt-4.1-mini"
    assert reason == "cost-optimal for simple triage tasks"


def test_resolve_infers_provider_from_pinned_model():
    provider, model, reason = resolve("autopilot_full", "balanced", "gpt-4.1")

    assert provider == "openai"
    assert model == "gpt-4.1"
    assert reason == "user-pinned model"


def test_resolve_honors_explicit_provider_override_without_pinned_model():
    provider, model, reason = resolve("pr_reviewer", "balanced", None, "openai")

    assert provider == "openai"
    assert model == "gpt-4.1-mini"
    assert reason == "openai override: efficient model for code review"


def test_resolve_falls_back_for_unknown_slug_by_preference():
    provider, model, reason = resolve("unknown_slug", "speed")

    assert provider == "openai"
    assert model == "gpt-4.1-mini"
    assert reason == "speed preference: efficient model"