"""Shared provider transport registry for internal and gateway LLM calls.

The first transport deliberately preserves the existing implementations:
internal callers still receive the current normalized SDK adapters, while the
gateway still forwards native provider bytes through ``app.guard.router``.
Future transports (for example LiteLLM) can replace either provider binding
without changing callers or moving credentials into profile configuration.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ProviderTransport(Protocol):
    """Capabilities shared by normalized clients and native gateway traffic."""

    name: str

    def create_client(
        self,
        *,
        provider: str,
        api_key: str,
        pricing_snapshot: dict[str, Any] | None = None,
        base_url: str | None = None,
    ) -> Any: ...

    async def forward(
        self,
        *,
        sender: Callable[..., Awaitable[Any]] | None = None,
        **kwargs: Any,
    ) -> Any: ...


class RawHTTPTransport:
    """Current direct-provider behavior behind the shared transport contract."""

    name = "raw_http"

    def create_client(
        self,
        *,
        provider: str,
        api_key: str,
        pricing_snapshot: dict[str, Any] | None = None,
        base_url: str | None = None,
    ) -> Any:
        if provider == "anthropic":
            from app.runtime.adapters.anthropic import AnthropicClient

            cls = AnthropicClient
        elif provider == "openai":
            from app.runtime.adapters.openai import OpenAIClient

            cls = OpenAIClient
        elif provider == "perplexity":
            from app.runtime.adapters.perplexity import PerplexityClient

            cls = PerplexityClient
        elif provider == "together":
            from app.runtime.adapters.together import TogetherClient

            cls = TogetherClient
        else:
            raise ValueError(
                f"Unknown LLM provider: {provider!r}. Expected one of: "
                "anthropic, openai, perplexity, together"
            )
        return cls(
            api_key=api_key,
            pricing_snapshot=pricing_snapshot,
            base_url=base_url,
        )

    async def forward(
        self,
        *,
        sender: Callable[..., Awaitable[Any]] | None = None,
        **kwargs: Any,
    ) -> Any:
        if sender is None:
            from app.guard.router import upstream

            sender = upstream
        return await sender(**kwargs)


class ProviderTransportRegistry:
    """Maps provider/profile slugs to replaceable transport implementations."""

    def __init__(self) -> None:
        self._transports: dict[str, ProviderTransport] = {}
        self._provider_bindings: dict[str, str] = {}

    def register(
        self,
        transport: ProviderTransport,
        *,
        providers: tuple[str, ...] = (),
        replace: bool = False,
    ) -> None:
        if transport.name in self._transports and not replace:
            raise ValueError(f"Transport already registered: {transport.name}")
        self._transports[transport.name] = transport
        for provider in providers:
            normalized = provider.strip().lower()
            if normalized in self._provider_bindings and not replace:
                raise ValueError(f"Provider transport already registered: {normalized}")
            self._provider_bindings[normalized] = transport.name

    def bind(self, provider: str, transport_name: str) -> None:
        if transport_name not in self._transports:
            raise ValueError(f"Unknown provider transport: {transport_name}")
        self._provider_bindings[provider.strip().lower()] = transport_name

    def for_provider(self, provider: str) -> ProviderTransport:
        normalized = provider.strip().lower()
        transport_name = self._provider_bindings.get(normalized)
        if transport_name is None:
            raise ValueError(f"No transport registered for provider: {normalized!r}")
        return self._transports[transport_name]


_registry = ProviderTransportRegistry()
_registry.register(
    RawHTTPTransport(),
    providers=("anthropic", "openai", "perplexity", "together", "litellm"),
)


def get_provider_transport_registry() -> ProviderTransportRegistry:
    return _registry
