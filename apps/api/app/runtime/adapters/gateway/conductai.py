"""ConductAI default gateway — no upstream URL set.

Auth is handled by the member token in the proxy layer; no extra headers needed.
"""


def headers(api_key: str, provider: str) -> dict:
    return {}
