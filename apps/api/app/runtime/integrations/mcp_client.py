"""
MCP client — tool discovery and execution.
Supports HTTP (Streamable) and SSE transports with auto-fallback.
"""
from __future__ import annotations
import asyncio
import json
from typing import Any


def _run(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result(timeout=30)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _list_tools_http(server_url: str, token: str | None) -> list[dict]:
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with streamablehttp_client(server_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [{"name": t.name, "description": t.description or "", "inputSchema": t.inputSchema if isinstance(t.inputSchema, dict) else {}} for t in result.tools]


async def _list_tools_sse(server_url: str, token: str | None) -> list[dict]:
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with sse_client(server_url, headers=headers) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return [{"name": t.name, "description": t.description or "", "inputSchema": t.inputSchema if isinstance(t.inputSchema, dict) else {}} for t in result.tools]


def list_tools(server_url: str, token: str | None = None, transport: str = "auto") -> tuple[list[dict], str]:
    if transport == "http":
        return _run(_list_tools_http(server_url, token)), "http"
    if transport == "sse":
        return _run(_list_tools_sse(server_url, token)), "sse"
    try:
        return _run(_list_tools_http(server_url, token)), "http"
    except Exception:
        return _run(_list_tools_sse(server_url, token)), "sse"


async def _call_tool_http(server_url: str, token: str | None, tool_name: str, tool_input: dict) -> Any:
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with streamablehttp_client(server_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=tool_input)
            parts = [c.text for c in result.content if hasattr(c, "text")]
            combined = "\n".join(parts)
            try:
                return json.loads(combined)
            except Exception:
                return combined


async def _call_tool_sse(server_url: str, token: str | None, tool_name: str, tool_input: dict) -> Any:
    from mcp.client.session import ClientSession
    from mcp.client.sse import sse_client
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with sse_client(server_url, headers=headers) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=tool_input)
            parts = [c.text for c in result.content if hasattr(c, "text")]
            combined = "\n".join(parts)
            try:
                return json.loads(combined)
            except Exception:
                return combined


def call_tool(server_url: str, token: str | None, tool_name: str, tool_input: dict, transport: str = "auto") -> Any:
    if transport == "http":
        return _run(_call_tool_http(server_url, token, tool_name, tool_input))
    if transport == "sse":
        return _run(_call_tool_sse(server_url, token, tool_name, tool_input))
    try:
        return _run(_call_tool_http(server_url, token, tool_name, tool_input))
    except Exception:
        return _run(_call_tool_sse(server_url, token, tool_name, tool_input))
