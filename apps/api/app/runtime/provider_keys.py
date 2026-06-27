"""Single source of truth for LLM provider key lookup.

Used by /workflows/{id}/validate preflight AND brain_block runtime so the
same check runs in both places — preflight catches it in canvas, brain_block
catches it for CLI/webhook runs.
"""
from __future__ import annotations

ENV_VAR = {
    "anthropic":  "ANTHROPIC_API_KEY",
    "openai":     "OPENAI_API_KEY",
    "perplexity": "PERPLEXITY_API_KEY",
}


def provider_for_model(model: str) -> str:
    m = (model or "").lower()
    if m.startswith("gpt-"):
        return "openai"
    if m.startswith("sonar"):
        return "perplexity"
    return "anthropic"


def provider_key_exists(provider: str, env_keys: set[str]) -> bool:
    """True if provider's key is present in env_keys or platform settings."""
    env_var = ENV_VAR[provider]
    return env_var in env_keys


class MissingProviderKey(RuntimeError):
    """Raised when a brain block's provider has no API key configured."""
    def __init__(self, provider: str, model: str = ""):
        self.provider = provider
        self.model = model
        self.env_var = ENV_VAR[provider]
        super().__init__(
            f"{self.env_var} is not set for {provider} model "
            f"'{model or 'default'}' — add it under Settings → Environments"
        )
