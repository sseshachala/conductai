"""Worker-lifetime singletons for the v2 gateway transports (X5).

Before this module, ``_execute_v2`` called ``AttemptCoordinator()``
per request, which constructed a new ``NativeHTTPTransport`` +
``LiteLLMTransport`` + ``HTTPPassthroughTransport`` on every request.
Each transport carried its own ``httpx.AsyncClient`` with an internal
connection pool. The "shared pool" the transport docstrings claimed
was actually per-instance — i.e. per-request. Zero connection reuse
across requests, and the worker-wide connection bound
(``max_connections=100``) was never enforced against real traffic.

This module holds one instance of each transport (and one
``AttemptCoordinator`` wrapping them) per worker process. Lazy
initialisation keeps import cost predictable in tests that don't
touch the network; ``shutdown()`` closes each transport's client so
graceful termination releases the pool cleanly.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from app.runtime.attempt_coordinator import AttemptCoordinator
    from app.runtime.http_passthrough_transport import HTTPPassthroughTransport
    from app.runtime.litellm_transport import LiteLLMTransport
    from app.runtime.native_http_transport import NativeHTTPTransport


log = structlog.get_logger(__name__)


_coordinator: "AttemptCoordinator | None" = None
_native: "NativeHTTPTransport | None" = None
_litellm: "LiteLLMTransport | None" = None
_passthrough: "HTTPPassthroughTransport | None" = None
_lock = asyncio.Lock()


async def get_coordinator() -> "AttemptCoordinator":
    """Return the worker-lifetime ``AttemptCoordinator`` singleton.

    Builds all three transports on first call under an asyncio.Lock
    so concurrent request handlers can't race and construct duplicate
    instances. Subsequent calls reuse the same instances — that's the
    whole point of the module.
    """
    global _coordinator, _native, _litellm, _passthrough

    if _coordinator is not None:
        return _coordinator

    async with _lock:
        # Double-check inside the lock — another coroutine may have
        # completed initialisation while we were waiting.
        if _coordinator is not None:
            return _coordinator

        from app.runtime.attempt_coordinator import AttemptCoordinator
        from app.runtime.http_passthrough_transport import HTTPPassthroughTransport
        from app.runtime.litellm_transport import LiteLLMTransport
        from app.runtime.native_http_transport import NativeHTTPTransport

        _native = NativeHTTPTransport()
        _litellm = LiteLLMTransport()
        _passthrough = HTTPPassthroughTransport()
        _coordinator = AttemptCoordinator(
            sdk_transport=_litellm,
            native_http_transport=_native,
            http_passthrough_transport=_passthrough,
        )
        log.info("gateway.v2.transports.singleton_initialised")

    return _coordinator


async def shutdown() -> None:
    """Close each transport's httpx client. Idempotent.

    Called from the FastAPI app's shutdown event so the underlying
    connection pool releases cleanly on graceful termination.
    Individual close failures are logged but never raise — shutdown
    must complete.
    """
    global _coordinator, _native, _litellm, _passthrough

    for transport in (_native, _litellm, _passthrough):
        if transport is None:
            continue
        client = getattr(transport, "_client", None)
        if client is None:
            continue
        try:
            await client.aclose()
        except Exception as exc:  # noqa: BLE001 — shutdown must not raise
            log.warning(
                "gateway.v2.transports.aclose_failed",
                transport=type(transport).__name__,
                err=str(exc),
            )

    _coordinator = None
    _native = None
    _litellm = None
    _passthrough = None


def _reset_for_tests() -> None:
    """Test-only helper — drop the cached singletons so each test can
    exercise ``get_coordinator``'s lazy-init path cleanly. Not exported
    via ``__all__``."""
    global _coordinator, _native, _litellm, _passthrough
    _coordinator = None
    _native = None
    _litellm = None
    _passthrough = None


__all__ = ["get_coordinator", "shutdown"]
