"""Gateway adapter factory.

Usage:
    from app.runtime.adapters.gateway import gateway_headers
    extra = gateway_headers(upstream_url, api_key, provider)
"""

from __future__ import annotations


def gateway_headers(upstream_url: str | None, api_key: str, provider: str) -> dict:
    """Detect gateway from upstream URL and return appropriate auth headers.

    Detection rules (first match wins):
    - None / empty  → conductai (default, no extra headers)
    - portkey.ai    → portkey
    - helicone.ai   → helicone
    - .azure.com or "azure" in url → azure
    - anything else → litellm (generic passthrough)
    """
    url = (upstream_url or "").lower()

    if not url:
        from app.runtime.adapters.gateway import conductai
        return conductai.headers(api_key, provider)

    if "portkey.ai" in url:
        from app.runtime.adapters.gateway import portkey
        return portkey.headers(api_key, provider)

    if "helicone.ai" in url:
        from app.runtime.adapters.gateway import helicone
        return helicone.headers(api_key, provider)

    if ".azure.com" in url or "azure" in url:
        from app.runtime.adapters.gateway import azure
        return azure.headers(api_key, provider)

    from app.runtime.adapters.gateway import litellm
    return litellm.headers(api_key, provider)
