"""Portkey AI gateway adapter."""

from __future__ import annotations

from app.runtime.adapters.gateway._types import GatewayConfig


def adapt(api_key: str, provider: str, model: str) -> GatewayConfig:
    return GatewayConfig(
        headers={
            "x-portkey-api-key": api_key,
            "x-portkey-provider": provider,
        },
        model=model,
    )
