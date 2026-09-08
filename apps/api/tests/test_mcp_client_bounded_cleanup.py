"""Bounded cleanup for the MCP client — regression coverage for #1728.

Some MCP servers (including our own /guard/mcp SSE endpoint) hold the
connection open with keepalive pings and never respond to client-side
close. Before this fix every RPC paid the outer 30s _run timeout on
teardown even though the tool call itself succeeded in milliseconds.

These tests use bare async context managers — no MCP SDK, no network —
to prove that _run_session enforces the cleanup ceiling and preserves
the RPC result even when __aexit__ hangs.
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock

import pytest

from app.runtime.integrations import mcp_client


class _HangingTransport:
    """Async context manager whose __aexit__ hangs forever.

    Mirrors the shape of streamablehttp_client / sse_client — yields a tuple
    whose first two elements are (read, write). The hang on exit is the
    bug we're guarding against.
    """

    def __init__(self, hang_seconds: float = 300.0):
        self.hang_seconds = hang_seconds
        self.exit_started = False

    async def __aenter__(self):
        return ("read-stub", "write-stub", "extras-stub")

    async def __aexit__(self, exc_type, exc, tb):
        self.exit_started = True
        await asyncio.sleep(self.hang_seconds)


class _FastTransport:
    """Async context manager that exits cleanly. Baseline sanity."""

    def __init__(self):
        self.exited = False

    async def __aenter__(self):
        return ("read-stub", "write-stub", "extras-stub")

    async def __aexit__(self, exc_type, exc, tb):
        self.exited = True


class _FakeSession:
    """Stand-in for mcp.client.session.ClientSession — no real transport work."""

    def __init__(self, read, write):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

    async def initialize(self):
        pass


@pytest.fixture(autouse=True)
def _patch_client_session(monkeypatch):
    """_run_session imports ClientSession lazily — patch that import path."""
    fake_module = MagicMock()
    fake_module.ClientSession = _FakeSession
    monkeypatch.setitem(
        __import__("sys").modules,
        "mcp.client.session",
        fake_module,
    )
    yield


def test_run_session_returns_result_when_cleanup_hangs():
    """The bug fix: op succeeds, transport __aexit__ hangs — still return the result."""
    hanging = _HangingTransport(hang_seconds=300.0)

    async def op(session):
        return "rpc-result"

    started = time.monotonic()
    result = asyncio.run(mcp_client._run_session(lambda: hanging, op))
    elapsed = time.monotonic() - started

    assert result == "rpc-result"
    assert hanging.exit_started, "cleanup should have been attempted"
    # cleanup ceiling is 1s — allow a little scheduler slack
    assert elapsed < 3.0, f"took {elapsed:.2f}s — cleanup ceiling not enforced"


def test_run_session_fast_transport_completes_in_microseconds():
    """Baseline: clean transport should not pay the cleanup ceiling."""
    fast = _FastTransport()

    async def op(session):
        return "quick"

    started = time.monotonic()
    result = asyncio.run(mcp_client._run_session(lambda: fast, op))
    elapsed = time.monotonic() - started

    assert result == "quick"
    assert fast.exited is True
    assert elapsed < 0.5, f"clean cleanup should be near-instant, took {elapsed:.2f}s"


def test_run_session_propagates_op_exceptions_after_cleanup():
    """If op raises, we still attempt cleanup, then re-raise the original error."""
    hanging = _HangingTransport(hang_seconds=300.0)

    class _RpcExplode(RuntimeError):
        pass

    async def op(session):
        raise _RpcExplode("simulated rpc failure")

    started = time.monotonic()
    with pytest.raises(_RpcExplode, match="simulated rpc failure"):
        asyncio.run(mcp_client._run_session(lambda: hanging, op))
    elapsed = time.monotonic() - started

    assert hanging.exit_started, "cleanup should still run on exception path"
    assert elapsed < 3.0, "exception path also bounded by cleanup ceiling"
