from app.runtime.adapters.gateway._types import GatewayConfig


def adapt(api_key: str, provider: str, model: str) -> GatewayConfig:
    # OpenRouter uses OpenAI-compatible Bearer auth (caller sets it) and
    # requires provider-prefixed model IDs, e.g. "anthropic/claude-3-5-haiku".
    base = model.split("/", 1)[-1] if "/" in model else model
    return GatewayConfig(headers={}, model=f"{provider}/{base}")
