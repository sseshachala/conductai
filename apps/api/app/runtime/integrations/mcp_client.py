"""
MCP client — tool discovery and execution.

Primary path is plain-httpx JSON-RPC 2.0 over POST. Works against any MCP
server that returns a JSON body on POST — including our own /mcp and
/guard/mcp endpoints, and any third-party server that implements the
Streamable HTTP transport without insisting on SSE. Cheap, fast, no SDK
session lifecycle to hang on.

SDK-based fallbacks (streamablehttp_client, sse_client) are kept for
servers that ONLY expose a streaming transport and can't answer a plain
POST. For those we still apply the 1s cleanup ceiling from #1728.
"""
from __future__ import annotations
import asyncio
import json
import uuid
from contextlib import AsyncExitStack
from typing import Any, Awaitable, Callable

import httpx


# ponytail: cleanup ceiling for bounded __aexit__ (issue #1728). Some MCP
# servers (including our own /guard/mcp SSE endpoint) hold the connection
# open with keepalive pings and never respond to client-side close. Without
# this ceiling every RPC pays the outer 30s _run timeout on teardown even
# though the tool call itself succeeded in milliseconds.
_CLEANUP_TIMEOUT_SECONDS = 1.0

# Total budget for a single POST — server should answer in ms; if it doesn't,
# either the URL is wrong or the server is down. Failing fast beats a 30s
# spinner that the user can't distinguish from success.
_HTTP_TIMEOUT_SECONDS = 10.0


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


# ── plain-httpx JSON-RPC path (primary) ───────────────────────────────────────


class _MCPError(Exception):
    """MCP server returned a JSON-RPC error envelope.

    Deliberately NOT RuntimeError — ``_run`` catches RuntimeError as its
    fallback for the missing-event-loop case, and would silently retry an
    MCP error as if it were a loop issue. Keep this in the pure Exception
    hierarchy so it propagates cleanly.
    """


async def _post_jsonrpc(server_url: str, token: str | None, method: str, params: dict) -> Any:
    """POST a single JSON-RPC 2.0 request, return the result field.

    Raises for HTTP status errors and for JSON-RPC error envelopes. No SSE,
    no session state, no SDK — just what the wire protocol actually is for
    a stateless request/response like tools/list or tools/call.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = {
        "jsonrpc": "2.0",
        "id": str(uuid.uuid4()),
        "method": method,
        "params": params,
    }
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post(server_url, headers=headers, json=body)
    # Parse the body first — MCP servers return JSON-RPC error envelopes even on
    # HTTP 401 (invalid token), and we want that specific message, not a generic
    # HTTPStatusError. Only fall back to raise_for_status if the body isn't JSON.
    try:
        payload = response.json()
    except Exception:
        response.raise_for_status()
        raise _MCPError(f"MCP: server returned non-JSON body (HTTP {response.status_code})")
    if isinstance(payload, dict) and "error" in payload:
        err = payload["error"] or {}
        raise _MCPError(f"MCP {err.get('code', '?')}: {err.get('message', 'unknown')}")
    response.raise_for_status()
    return payload.get("result", {}) if isinstance(payload, dict) else {}


async def _list_tools_jsonrpc(server_url: str, token: str | None) -> list[dict]:
    result = await _post_jsonrpc(server_url, token, "tools/list", {})
    tools = result.get("tools", []) if isinstance(result, dict) else []
    return [
        {
            "name": t.get("name", ""),
            "description": t.get("description", "") or "",
            "inputSchema": t.get("inputSchema") if isinstance(t.get("inputSchema"), dict) else {},
        }
        for t in tools
    ]


async def _call_tool_jsonrpc(server_url: str, token: str | None, tool_name: str, tool_input: dict) -> Any:
    result = await _post_jsonrpc(
        server_url, token, "tools/call",
        {"name": tool_name, "arguments": tool_input},
    )
    if not isinstance(result, dict):
        return result
    # MCP tool responses shape: {"content": [{"type": "text", "text": "..."}, ...]}
    content = result.get("content") or []
    parts = [c.get("text", "") for c in content if isinstance(c, dict) and "text" in c]
    combined = "\n".join(parts) if parts else json.dumps(result)
    try:
        return json.loads(combined)
    except Exception:
        return combined


# ── SDK-based fallbacks (streamablehttp_client, sse_client) ───────────────────


async def _run_session(
    transport_factory: Callable[[], Any],
    op: Callable[[Any], Awaitable[Any]],
) -> Any:
    """SDK path with bounded cleanup — see issue #1728 for why."""
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


async def _list_tools_sse(server_url: str, token: str | None) -> list[dict]:
    from mcp.client.sse import sse_client
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    result = await _run_session(
        lambda: sse_client(server_url, headers=headers),
        lambda session: session.list_tools(),
    )
    return _tools_to_dicts(result.tools)


async def _call_tool_sse(server_url: str, token: str | None, tool_name: str, tool_input: dict) -> Any:
    from mcp.client.sse import sse_client
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    result = await _run_session(
        lambda: sse_client(server_url, headers=headers),
        lambda session: session.call_tool(tool_name, arguments=tool_input),
    )
    return _call_result_to_value(result)


# ── public entry points — auto tries plain HTTP first, SDK fallbacks after ────


def list_tools(server_url: str, token: str | None = None, transport: str = "auto") -> tuple[list[dict], str]:
    try:
        if transport == "sse":
            return _run(_list_tools_sse(server_url, token)), "sse"
        if transport == "http":
            return _run(_list_tools_jsonrpc(server_url, token)), "http"
        # auto: plain HTTP JSON-RPC first (works for /mcp, /guard/mcp, most
        # third-party MCP servers). Fall back to SSE only if HTTP genuinely
        # fails (server doesn't answer POST, only supports streaming).
        try:
            return _run(_list_tools_jsonrpc(server_url, token)), "http"
        except _MCPError:
            # Server responded with a real JSON-RPC error (e.g. invalid token).
            # SSE fallback would produce the same error — don't waste 30s.
            raise
        except Exception:
            return _run(_list_tools_sse(server_url, token)), "sse"
    except BaseException as exc:
        raise _unwrap_exc(exc) from exc


def call_tool(server_url: str, token: str | None, tool_name: str, tool_input: dict, transport: str = "auto") -> Any:
    try:
        if transport == "sse":
            return _run(_call_tool_sse(server_url, token, tool_name, tool_input))
        if transport == "http":
            return _run(_call_tool_jsonrpc(server_url, token, tool_name, tool_input))
        try:
            return _run(_call_tool_jsonrpc(server_url, token, tool_name, tool_input))
        except _MCPError:
            raise
        except Exception:
            return _run(_call_tool_sse(server_url, token, tool_name, tool_input))
    except BaseException as exc:
        raise _unwrap_exc(exc) from exc
