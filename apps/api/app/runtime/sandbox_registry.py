"""
sandbox_registry — provider registry for SandboxSession backends.

Each backend decorates its class with @register("provider_name").
create_session() looks up the registry instead of using if/elif chains,
so adding a new backend is one file + one decorator with no changes here.

Usage:
    from app.runtime.sandbox_registry import register, get_provider

    @register("e2b")
    class E2BSession:
        @classmethod
        def from_config(cls, runs_on: dict, credentials: dict) -> "E2BSession":
            ...
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.runtime.sandbox_session import SandboxSession

_REGISTRY: dict[str, type] = {}


def register(provider: str):
    """Decorator — registers a session class under the given provider key."""
    def decorator(cls):
        _REGISTRY[provider] = cls
        return cls
    return decorator


def get_provider(provider: str) -> type:
    if provider not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"Unknown execution provider: {provider!r}. Available: {available}"
        )
    return _REGISTRY[provider]


def registered_providers() -> list[str]:
    return sorted(_REGISTRY)
