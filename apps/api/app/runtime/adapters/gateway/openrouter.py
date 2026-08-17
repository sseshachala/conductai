from app.runtime.adapters.gateway._types import GatewayConfig


def adapt(api_key: str, provider: str, model: str) -> GatewayConfig:
    # OpenRouter is OpenAI-compatible. Auth is Bearer with the OpenRouter key;
    # HTTP-Referer + X-Title are optional attribution headers that show up on
    # openrouter.ai/rankings. Model IDs must be provider-prefixed, e.g.
    # "anthropic/claude-3-5-haiku"; we rebuild the prefix idempotently.
    base = model.split("/", 1)[-1] if "/" in model else model
    return GatewayConfig(
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://conductai.ai",
            "X-Title": "Conduct",
        },
        model=f"{provider}/{base}" if (provider and base) else base,
    )
