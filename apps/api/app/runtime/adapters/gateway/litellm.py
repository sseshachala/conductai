"""LiteLLM generic/passthrough gateway adapter.

LiteLLM requires the model to be prefixed with the provider name,
e.g. "anthropic/claude-3-5-haiku-20241022". If not already prefixed,
this adapter rewrites the model string accordingly.
"""

from __future__ import annotations

from app.runtime.adapters.gateway._types import GatewayConfig


def adapt(api_key: str, provider: str, model: str) -> GatewayConfig:
    # LiteLLM requires provider prefix: "anthropic/claude-3-5-haiku-20241022"
    rewritten = model if model.startswith(f"{provider}/") else f"{provider}/{model}"
    return GatewayConfig(headers={}, model=rewritten)
