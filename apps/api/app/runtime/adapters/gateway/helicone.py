"""Helicone observability gateway adapter."""


def headers(api_key: str, provider: str) -> dict:
    return {"Helicone-Auth": f"Bearer {api_key}"}
