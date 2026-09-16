"""X5 — worker-lifetime transports for the v2 gateway.

Before the fix, ``_execute_v2`` called ``AttemptCoordinator()`` per
request. The coordinator constructed a new
``NativeHTTPTransport`` + ``LiteLLMTransport`` +
``HTTPPassthroughTransport`` on every request; each transport carried
its own ``httpx.AsyncClient``. The claimed shared pool was actually
per-instance — per-request in practice. No connection reuse across
requests; the ``max_connections=100`` cap was per-request, not
worker-wide.

Fixed by ``app.runtime.gateway_transports`` holding a lazy singleton
coordinator. This file locks:

- ``get_coordinator()`` returns the same instance on repeat calls
  (i.e. the pool is genuinely reused, not just re-instantiated with
  the same shape).
- ``shutdown()`` calls ``aclose()`` on each transport's underlying
  ``httpx.AsyncClient`` if one exists.
- The handler wires ``get_coordinator()`` instead of instantiating a
  new coordinator per request.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


_HANDLER_SRC = (
    Path(__file__).resolve().parents[2]
    / "app" / "modules" / "guard" / "gateway_handler.py"
).read_text(encoding="utf-8")


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Wipe the module-level singleton before + after each test so
    tests can exercise the lazy-init path deterministically."""
    from app.runtime import gateway_transports
    gateway_transports._reset_for_tests()
    yield
    gateway_transports._reset_for_tests()


@pytest.mark.anyio("asyncio")
async def test_get_coordinator_returns_same_instance_across_calls():
    """The whole point of the module: repeat calls return the SAME
    coordinator (and thus the same transports, thus the same client
    pool). If this ever regresses to a per-call construction, all
    the promised connection reuse vanishes."""
    from app.runtime.gateway_transports import get_coordinator

    coord_a = await get_coordinator()
    coord_b = await get_coordinator()
    coord_c = await get_coordinator()

    assert coord_a is coord_b is coord_c, (
        "get_coordinator must return a singleton — got distinct "
        "instances, meaning every request would rebuild the pool."
    )
    # The wrapped transports are the same instances too.
    assert coord_a._sdk is coord_b._sdk
    assert coord_a._native is coord_b._native
    assert coord_a._passthrough is coord_b._passthrough


@pytest.mark.anyio("asyncio")
async def test_shutdown_closes_httpx_clients_on_all_transports():
    """``shutdown()`` must call ``aclose()`` on each transport's
    lazily-created ``_client``. If we forget to close, workers leak
    connections across graceful restarts."""
    from app.runtime.gateway_transports import get_coordinator, shutdown

    coord = await get_coordinator()

    # Force each transport to lazily build its client, then swap in a
    # mock so we can observe aclose().
    async_mocks = []
    for name in ("_native", "_sdk", "_passthrough"):
        transport = getattr(coord, name)
        mock_client = MagicMock()
        mock_client.aclose = AsyncMock()
        transport._client = mock_client
        async_mocks.append(mock_client)

    await shutdown()

    for mc in async_mocks:
        mc.aclose.assert_awaited_once()


@pytest.mark.anyio("asyncio")
async def test_shutdown_is_idempotent_when_never_initialised():
    """A worker that only served v1 traffic never lazily built the
    coordinator. ``shutdown()`` must be a no-op in that case, not
    raise."""
    from app.runtime.gateway_transports import shutdown
    # Fixture wiped state; call shutdown without ever calling
    # get_coordinator first.
    await shutdown()   # must not raise


def test_handler_uses_singleton_getter_not_per_request_construction():
    """Source-scan: gateway_handler no longer calls
    ``_AttemptCoordinator()`` inline. It goes through
    ``get_coordinator`` so the pool stays worker-lifetime."""
    # The old inline construction is gone.
    assert "coordinator = _AttemptCoordinator()" not in _HANDLER_SRC, (
        "gateway_handler must NOT construct AttemptCoordinator per "
        "request. Use app.runtime.gateway_transports.get_coordinator()."
    )
    # The new singleton getter is wired.
    assert "get_coordinator" in _HANDLER_SRC, (
        "gateway_handler must import get_coordinator from "
        "app.runtime.gateway_transports so the transport pool is "
        "worker-lifetime."
    )
    assert "coordinator = await get_coordinator()" in _HANDLER_SRC


def test_app_registers_shutdown_hook_for_transports():
    """FastAPI shutdown event must call the transport shutdown so the
    connection pool releases on graceful termination."""
    main_src = (
        Path(__file__).resolve().parents[2]
        / "app" / "main.py"
    ).read_text(encoding="utf-8")
    assert '@app.on_event("shutdown")' in main_src, (
        "gateway transports need a shutdown hook so httpx clients "
        "aclose on graceful termination."
    )
    assert "from app.runtime.gateway_transports import shutdown" in main_src, (
        "shutdown handler must import the transport shutdown fn"
    )
