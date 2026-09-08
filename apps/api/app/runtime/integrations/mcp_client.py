"""
MCP client — tool discovery and execution.
Supports HTTP (Streamable) and SSE transports with auto-fallback.
"""
from __future__ import annotations
import asyncio
import json
from contextlib import AsyncExitStack
from typing import Any, Awaitable, Callable


# ponytail: cleanup ceiling for bounded __aexit__ (issue #1728). Some MCP
# servers (including our own /guard/mcp SSE endpoint) hold the connection
# open with keepalive pings and never respond to client-side close. Without
# this ceiling every RPC pays the outer 30s _run timeout on teardown even
# though the tool call itself succeeded in milliseconds. Real fix is
# server-side session lifecycle; this ceiling is the seatbelt for
# third-party MCP servers we don't control.
_CLEANUP_TIMEOUT_SECONDS = 1.0


def _unwrap_exc(exc: BaseException) -> BaseException:
    """anyio wraps connection errors in ExceptionGroup — extract the real cause."""
    excs = getattr(exc, "exceptions", None)
    if excs:
        return _unwrap_exc(excs[0])
    # SSEError from httpx_sse when the URL returns HTML instead of an event stream —
    # usually means the configured server_url is not an MCP SSE endpoint.
    if type(exc).__name__ == "SSEError" and "text/event-stream" in str(exc):
        return RuntimeError(
            "This MCP server URL does not expose an SSE endpoint "
            "(response Content-Type was not text/event-stream). "
            "Check the URL in your integration — it likely needs a specific path "
            "(e.g. /sse or /v1/messages/sse) rather than the base host."
        )
    return exc


def _run(coro, timeout: float = 30.0):
    # ponytail: asyncio.wait_for actually cancels the underlying I/O.
    # ThreadPoolExecutor.result(timeout=...) alone doesn't — its `with` __exit__
    # waits for the thread to finish, so a hung socket blocked the whole run (#1013).
    async def _bounded():
        return await asyncio.wait_for(coro, timeout=timeout)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, _bounded()).result(timeout=timeout + 5)
        return loop.run_until_complete(_bounded())
    except RuntimeError:
        return asyncio.run(_bounded())


async def _run_session(
    transport_factory: Callable[[], Any],
    op: Callable[[Any], Awaitable[Any]],
) -> Any:
    """Enter transport + ClientSession, run ``op(session)``, tear down safely.

    Cleanup is bounded to ``_CLEANUP_TIMEOUT_SECONDS`` — see issue #1728. If
    ``op`` succeeds and cleanup hangs (typical against keepalive-forever SSE
    servers), we still return the result. If cleanup succeeds normally, we
    exit in microseconds.

    ``transport_factory`` returns the transport context manager (called with
    no args). Each transport yields a tuple whose first two elements are
    ``(read, write)``.
    """
    from mcp.client.session import ClientSession

    stack = AsyncExitStack()
    try:
        transport = await stack.enter_async_context(transport_factory())
        read, write = transport[0], transport[1]
        session = await stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        return await op(session)
    finally:
        try:
            await asyncio.wait_for(stack.aclose(), timeout=_CLEANUP_TIMEOUT_SECONDS)
        except Exception:
            # ponytail: cleanup hangs are the whole reason this helper exists (#1728).
            # Losing the RPC result over a slow teardown is the bug we're fixing.
            pass


def _tools_to_dicts(tools) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "inputSchema": t.inputSchema if isinstance(t.inputSchema, dict) else {},
        }
        for t in tools
    ]


def _call_result_to_value(result) -> Any:
    parts = [c.text for c in result.content if hasattr(c, "text")]
    combined = "\n".join(parts)
    try:
        return json.loads(combined)
    except Exception:
        return combined


async def _list_tools_http(server_url: str, token: str | None) -> list[dict]:
    from mcp.client.streamable_http import streamablehttp_client
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    result = await _run_session(
        lambda: streamablehttp_client(server_url, headers=headers),
        lambda session: session.list_tools(),
    )
    return _tools_to_dicts(result.tools)


async def _list_tools_sse(server_url: str, token: str | None) -> list[dict]:
    from mcp.client.sse import sse_client
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    result = await _run_session(
        lambda: sse_client(server_url, headers=headers),
        lambda session: session.list_tools(),
    )
    return _tools_to_dicts(result.tools)


def list_tools(server_url: str, token: str | None = None, transport: str = "auto") -> tuple[list[dict], str]:
    try:
        if transport == "http":
            return _run(_list_tools_http(server_url, token)), "http"
        if transport == "sse":
            return _run(_list_tools_sse(server_url, token)), "sse"
        try:
            return _run(_list_tools_http(server_url, token)), "http"
        except Exception:
            return _run(_list_tools_sse(server_url, token)), "sse"
    except BaseException as exc:
        raise _unwrap_exc(exc) from exc


async def _call_tool_http(server_url: str, token: str | None, tool_name: str, tool_input: dict) -> Any:
    from mcp.client.streamable_http import streamablehttp_client
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    result = await _run_session(
        lambda: streamablehttp_client(server_url, headers=headers),
        lambda session: session.call_tool(tool_name, arguments=tool_input),
    )
    return _call_result_to_value(result)


async def _call_tool_sse(server_url: str, token: str | None, tool_name: str, tool_input: dict) -> Any:
    from mcp.client.sse import sse_client
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    result = await _run_session(
        lambda: sse_client(server_url, headers=headers),
        lambda session: session.call_tool(tool_name, arguments=tool_input),
    )
    return _call_result_to_value(result)


def call_tool(server_url: str, token: str | None, tool_name: str, tool_input: dict, transport: str = "auto") -> Any:
    try:
        if transport == "http":
            return _run(_call_tool_http(server_url, token, tool_name, tool_input))
        if transport == "sse":
            return _run(_call_tool_sse(server_url, token, tool_name, tool_input))
        try:
            return _run(_call_tool_http(server_url, token, tool_name, tool_input))
        except Exception:
            return _run(_call_tool_sse(server_url, token, tool_name, tool_input))
    except BaseException as exc:
        raise _unwrap_exc(exc) from exc
