"""MCPCore — transport-agnostic dispatcher for JSON-RPC 2.0 MCP requests.

Handles the standard MCP methods (initialize / tools/list / tools/call /
notifications/initialized / ping) using a ToolRegistry as the source of
truth for tools. Speaks MCP protocol 2026-07-28 by default; echoes the
client's requested version to stay compatible with older clients.

Adapters (mcp.http / mcp.stdio) supply the request + ToolContext, receive
a response dict, and translate it to their transport (HTTP JSONResponse
vs stdio stdout line).

Every tools/call dispatch runs the tool through the composable policy
engine (#1225) before invoking impl — same shape as Executor.call in
#1218 Step 4. No adapter can bypass policy.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import structlog

from app.guard.policy import evaluate_composed
from app.guard.policy_types import PolicyAction, PolicyContext
from app.tools.registry import ToolRegistry
from app.tools.types import ToolDef

log = structlog.get_logger(__name__)

PROTOCOL_VERSION_DEFAULT = "2026-07-28"
SERVER_NAME = "conduct"
SERVER_VERSION = "1.0.0"

# JSON-RPC 2.0 error codes
_ERR_PARSE = -32700
_ERR_INVALID_REQUEST = -32600
_ERR_METHOD_NOT_FOUND = -32601
_ERR_INVALID_PARAMS = -32602
_ERR_INTERNAL = -32603


@dataclass
class MCPContext:
    """Runtime context every tool call has access to.

    Adapters build this from their transport auth (Bearer token → workspace_id,
    OAuth → clerk_user_id, etc.). Tools read but never mutate.

    Enriched fields (user_email/session_id/resolved_token) are populated by
    adapters that support them — Lens tools ignore them, guard tools need
    them for audit attribution and HITL approval flow (#1219 Phase 3b B2).
    """
    workspace_id: str
    clerk_user_id: str | None = None
    surface: str = "unknown"     # claude.ai / claude-code / cursor / windsurf / vscode / stdio / http
    user_email: str | None = None
    session_id: str | None = None
    resolved_token: str = ""      # raw Bearer — guard_enable echoes it back to the user


def _ok(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _err(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _text_result(text: str) -> dict[str, Any]:
    """MCP tools/call result body — one text content block."""
    return {"content": [{"type": "text", "text": text}]}


def _structured_result(text: str, structured: Any) -> dict[str, Any]:
    """MCP 2026-07-28 structuredContent — pair a text summary with a
    machine-readable payload."""
    return {
        "content": [{"type": "text", "text": text}],
        "structuredContent": structured,
    }


def dispatch(
    request: dict[str, Any],
    ctx: MCPContext,
    registry: ToolRegistry,
) -> dict[str, Any] | None:
    """Handle one JSON-RPC 2.0 MCP request.

    Returns the response dict (adapter serialises to transport), or None
    for notifications (no reply expected).
    """
    method = request.get("method")
    msg_id = request.get("id")
    params = request.get("params") or {}

    if method == "initialize":
        return _handle_initialize(msg_id, params)

    if method == "notifications/initialized":
        return None  # notification, no response

    if method == "ping":
        return _ok(msg_id, {})

    if method == "tools/list":
        return _handle_tools_list(msg_id, registry)

    if method == "tools/call":
        return _handle_tools_call(msg_id, params, ctx, registry)

    return _err(msg_id, _ERR_METHOD_NOT_FOUND, f"Method not found: {method!r}")


def _handle_initialize(msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Return capabilities + serverInfo + optional instructions."""
    negotiated_version = params.get("protocolVersion") or PROTOCOL_VERSION_DEFAULT
    client_info = params.get("clientInfo") or {}
    result = {
        "protocolVersion": negotiated_version,
        "capabilities": {
            # tools/list supports listChanged notifications in this server
            "tools": {"listChanged": False},
        },
        "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        "instructions": (
            "Conduct MCP is active — policy engine + audit chain apply to every "
            "tool call. Call guard_activity ONCE at the start of a user request with "
            "a one-line summary. Call guard_check ONCE per intent. If a response is "
            "BLOCKED: stop and surface the rule to the user."
        ),
        # Non-spec metadata — Conduct extension
        "_surface": _detect_surface(client_info),
    }
    return _ok(msg_id, result)


def _handle_tools_list(msg_id: Any, registry: ToolRegistry) -> dict[str, Any]:
    """Project the registry onto the MCP tools/list response shape."""
    return _ok(msg_id, {
        "tools": registry.as_mcp_tools_list(),
        # 2026-07-28 spec — cacheable list result
        "ttlMs": 60_000,
        "cacheScope": "workspace",
    })


def _handle_tools_call(
    msg_id: Any,
    params: dict[str, Any],
    ctx: MCPContext,
    registry: ToolRegistry,
) -> dict[str, Any]:
    """Look up tool, run through composable policy engine, dispatch."""
    tool_name = params.get("name")
    arguments = params.get("arguments") or {}

    if not tool_name or not isinstance(tool_name, str):
        return _err(msg_id, _ERR_INVALID_PARAMS, "params.name is required")

    tool = registry.get(tool_name)
    if tool is None:
        # MCP convention: return an error via the result envelope (isError=true)
        # rather than a JSON-RPC error, so the LLM sees a tool-level failure.
        return _ok(msg_id, {
            **_text_result(f"[ws:{ctx.workspace_id[:8]}] Unknown tool: {tool_name}"),
            "isError": True,
        })

    # Per-tool policy gate — same shape as Executor.call in #1218 Step 4.
    policy_ctx = PolicyContext(
        workspace_id=ctx.workspace_id,
        clerk_user_id=ctx.clerk_user_id,
        provider="mcp",
        model="tool",
        body={"tool_name": tool_name, "arguments": arguments},
        extras={"kind": "mcp_tool", "tool_name": tool_name, "surface": ctx.surface},
    )
    try:
        decision = evaluate_composed(policy_ctx)
    except Exception as e:
        log.warning("mcp.policy_eval.failed", tool=tool_name, err=str(e))
        decision = None

    if decision is not None and decision.action == PolicyAction.BLOCK:
        log.warning("mcp.tool.blocked",
                    tool=tool_name,
                    rule=decision.rule_id,
                    source=decision.source)
        return _ok(msg_id, {
            **_text_result(
                f"Blocked by Guard rule {decision.rule_id}: "
                f"{decision.reason or 'policy violation'}"
            ),
            "isError": True,
            "_blockedBy": decision.source,
            "_ruleId": decision.rule_id,
        })

    return _invoke_tool(msg_id, tool, arguments, ctx)


def _invoke_tool(
    msg_id: Any,
    tool: ToolDef,
    arguments: dict[str, Any],
    ctx: MCPContext,
) -> dict[str, Any]:
    """Run the tool impl, translate return value into MCP response shape."""
    try:
        result = tool.impl(ctx=ctx, **arguments) if _accepts_ctx(tool.impl) else tool.impl(**arguments)
    except TypeError as e:
        return _ok(msg_id, {
            **_text_result(f"Invalid arguments for {tool.name!r}: {e}"),
            "isError": True,
        })
    except Exception as e:
        log.warning("mcp.tool.exception", tool=tool.name, err=str(e))
        return _ok(msg_id, {
            **_text_result(f"Tool {tool.name!r} failed: {e}"),
            "isError": True,
        })

    # If the tool returned a dict, expose it as both a text summary + machine
    # payload (2026-07-28 structuredContent). Strings become plain text.
    if isinstance(result, str):
        return _ok(msg_id, _text_result(result))
    if isinstance(result, (dict, list)):
        import json as _json
        text = _json.dumps(result, default=str)[:2000]
        return _ok(msg_id, _structured_result(text, result))
    return _ok(msg_id, _text_result(str(result)))


def _accepts_ctx(impl) -> bool:
    """True if the tool impl accepts a `ctx` kwarg."""
    import inspect
    try:
        sig = inspect.signature(impl)
        return "ctx" in sig.parameters
    except (TypeError, ValueError):
        return False


def _detect_surface(client_info: dict[str, Any]) -> str:
    """Best-effort surface detection from clientInfo.name / version."""
    name = (client_info.get("name") or "").lower()
    if "claude" in name and "desktop" not in name and "code" not in name:
        return "claude.ai"
    if "claude-code" in name or "claude_code" in name:
        return "claude-code"
    if "cursor" in name:
        return "cursor"
    if "windsurf" in name or "codeium" in name:
        return "windsurf"
    if "vscode" in name or "copilot" in name:
        return "vscode"
    if "codex" in name:
        return "codex"
    if "desktop" in name:
        return "claude-desktop"
    return "unknown"


def new_session_id() -> str:
    """Return a fresh Mcp-Session-Id for the streamable HTTP transport.

    Adapters pass this back in the response header. We're stateless — any
    stable-per-response uuid satisfies the contract."""
    return str(uuid.uuid4())
