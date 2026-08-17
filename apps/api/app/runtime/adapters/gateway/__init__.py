"""Gateway adapter factory.

Usage:
    from app.runtime.adapters.gateway import gateway_adapt, GatewayConfig
    gw = gateway_adapt(upstream_url, api_key, provider, model_id)
    # gw.headers — dict of extra headers for the LLM client
    # gw.model   — final model name (may be rewritten by the gateway)

Backward-compat shim:
    from app.runtime.adapters.gateway import gateway_headers
    extra = gateway_headers(upstream_url, api_key, provider)
"""

from __future__ import annotations

from app.runtime.adapters.gateway._types import GatewayConfig

__all__ = ["GatewayConfig", "gateway_adapt", "gateway_headers"]


def gateway_adapt(
    upstream_url: str | None,
    api_key: str,
    provider: str,
    model: str,
) -> GatewayConfig:
    """Detect gateway from upstream URL, return headers + final model name.

    Detection rules (first match wins):
    - None / empty       → conductai (default, no extra headers)
    - portkey.ai         → portkey
    - helicone.ai        → helicone
    - openrouter.ai      → openrouter
    - .azure.com / azure → azure
    - anything else      → litellm (generic passthrough, rewrites model)
    """
    url = (upstream_url or "").lower()

    if not url:
        from app.runtime.adapters.gateway import conductai
        return conductai.adapt(api_key, provider, model)

    if "portkey.ai" in url:
        from app.runtime.adapters.gateway import portkey
        return portkey.adapt(api_key, provider, model)

    if "helicone.ai" in url:
        from app.runtime.adapters.gateway import helicone
        return helicone.adapt(api_key, provider, model)

    if "openrouter.ai" in url:
        from app.runtime.adapters.gateway import openrouter
        return openrouter.adapt(api_key, provider, model)

    if ".azure.com" in url or "azure" in url:
        from app.runtime.adapters.gateway import azure
        return azure.adapt(api_key, provider, model)

    from app.runtime.adapters.gateway import litellm
    return litellm.adapt(api_key, provider, model)


def gateway_headers(upstream_url: str | None, api_key: str, provider: str) -> dict:
    """Backward-compat shim — returns only the headers dict."""
    return gateway_adapt(upstream_url, api_key, provider, "").headers
