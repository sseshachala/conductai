"""Portkey AI gateway adapter."""


def headers(api_key: str, provider: str) -> dict:
    return {
        "x-portkey-api-key": api_key,
        "x-portkey-provider": provider,
    }
