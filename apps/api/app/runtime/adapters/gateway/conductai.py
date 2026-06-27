"""ConductAI default gateway — no upstream URL set.

Auth is handled by the member token in the proxy layer; no extra headers needed.
"""

from __future__ import annotations

from app.runtime.adapters.gateway._types import GatewayConfig


def adapt(api_key: str, provider: str, model: str) -> GatewayConfig:
    return GatewayConfig(headers={}, model=model)
