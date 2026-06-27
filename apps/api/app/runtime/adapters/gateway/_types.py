"""Shared types for gateway adapters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GatewayConfig:
    headers: dict
    model: str  # possibly rewritten by the gateway
