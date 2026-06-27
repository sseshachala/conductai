"""LiteLLM generic/passthrough gateway adapter.

LiteLLM accepts the standard Authorization header from the underlying client;
no extra headers are needed.
"""


def headers(api_key: str, provider: str) -> dict:
    return {}
