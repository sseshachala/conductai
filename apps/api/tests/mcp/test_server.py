"""MCPCore dispatcher unit tests — #1219 Phase 2."""
from __future__ import annotations

from unittest.mock import patch

from app.guard.policy_types import PolicyAction, PolicyDecision
from app.mcp.server import (
    MCPContext,
    PROTOCOL_VERSION_DEFAULT,
    SERVER_NAME,
    dispatch,
    new_session_id,
)
from app.tools.registry import ToolRegistry
from app.tools.types import ToolAnnotations, ToolDef


def _ctx(**over) -> MCPContext:
    base = dict(
        workspace_id="00000000-0000-0000-0000-000000000001",
        clerk_user_id="user_test",
        surface="test",
    )
    base.update(over)
    return MCPContext(**base)


def _registry_with(tools: list[ToolDef]) -> ToolRegistry:
    r = ToolRegistry()
    r.register_all(tools)
    return r


def _tool(name="example", impl=None, **over) -> ToolDef:
    return ToolDef(
        name=name,
        description=f"{name} description",
        input_schema={"type": "object", "properties": {}},
        impl=impl or (lambda: {"ok": True}),
        **over,
    )


def _allow_decision():
    return PolicyDecision(action=PolicyAction.ALLOW, source="rule")


def _block_decision():
    return PolicyDecision(
        action=PolicyAction.BLOCK,
        source="rule",
        rule_id="mcp.no_secret_search",
        reason="Blocked search for secrets",
    )


# ─── initialize ──────────────────────────────────────────────────────────────

def test_initialize_returns_capabilities_and_server_info():
    request = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL_VERSION_DEFAULT,
            "clientInfo": {"name": "regression-harness", "version": "0.0.1"},
        },
    }
    response = dispatch(request, _ctx(), ToolRegistry())
    assert response["id"] == 1
    result = response["result"]
    assert result["protocolVersion"] == PROTOCOL_VERSION_DEFAULT
    assert result["serverInfo"]["name"] == SERVER_NAME
    assert "capabilities" in result
    assert "instructions" in result


def test_initialize_echoes_client_protocol_version():
    request = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "clientInfo": {}},
    }
    response = dispatch(request, _ctx(), ToolRegistry())
    assert response["result"]["protocolVersion"] == "2024-11-05"


def test_initialize_detects_surface_from_client_info():
    request = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"clientInfo": {"name": "cursor-mcp-client"}},
    }
    response = dispatch(request, _ctx(), ToolRegistry())
    assert response["result"]["_surface"] == "cursor"


# ─── notifications ───────────────────────────────────────────────────────────

def test_notifications_initialized_returns_none():
    request = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    assert dispatch(request, _ctx(), ToolRegistry()) is None


def test_ping_returns_empty_result():
    request = {"jsonrpc": "2.0", "id": 99, "method": "ping"}
    response = dispatch(request, _ctx(), ToolRegistry())
    assert response == {"jsonrpc": "2.0", "id": 99, "result": {}}


# ─── tools/list ──────────────────────────────────────────────────────────────

def test_tools_list_projects_registry():
    registry = _registry_with([_tool("a"), _tool("b")])
    request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    response = dispatch(request, _ctx(), registry)
    tools = response["result"]["tools"]
    assert len(tools) == 2
    assert {t["name"] for t in tools} == {"a", "b"}


def test_tools_list_includes_cacheable_metadata():
    request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    response = dispatch(request, _ctx(), ToolRegistry())
    assert response["result"]["ttlMs"] == 60_000
    assert response["result"]["cacheScope"] == "workspace"


def test_tools_list_includes_annotations():
    registry = _registry_with([
        _tool("read", annotations=ToolAnnotations(read_only=True, idempotent=True)),
    ])
    request = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    tools = dispatch(request, _ctx(), registry)["result"]["tools"]
    assert tools[0]["annotations"]["readOnly"] is True
    assert tools[0]["annotations"]["idempotent"] is True


# ─── tools/call ──────────────────────────────────────────────────────────────

def test_tools_call_unknown_tool_returns_error_envelope():
    request = {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "does_not_exist"},
    }
    with patch("app.mcp.server.evaluate_composed", return_value=_allow_decision()):
        response = dispatch(request, _ctx(), ToolRegistry())
    result = response["result"]
    assert result["isError"] is True
    assert "Unknown tool" in result["content"][0]["text"]


def test_tools_call_missing_name_returns_invalid_params():
    request = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {}}
    response = dispatch(request, _ctx(), ToolRegistry())
    assert response["error"]["code"] == -32602
    assert "params.name" in response["error"]["message"]


def test_tools_call_runs_allowed_tool_string_result():
    def impl():
        return "hello"
    registry = _registry_with([_tool("say_hi", impl=impl)])
    request = {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "say_hi"},
    }
    with patch("app.mcp.server.evaluate_composed", return_value=_allow_decision()):
        response = dispatch(request, _ctx(), registry)
    result = response["result"]
    assert result["content"][0]["text"] == "hello"
    assert "isError" not in result


def test_tools_call_runs_allowed_tool_dict_result_with_structured_content():
    def impl():
        return {"answer": 42, "extra": "stuff"}
    registry = _registry_with([_tool("compute", impl=impl)])
    request = {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "compute"},
    }
    with patch("app.mcp.server.evaluate_composed", return_value=_allow_decision()):
        response = dispatch(request, _ctx(), registry)
    result = response["result"]
    assert result["structuredContent"] == {"answer": 42, "extra": "stuff"}
    assert "42" in result["content"][0]["text"]


def test_tools_call_blocked_by_policy_returns_error_envelope():
    def impl():
        return "should not run"
    called = []
    def watched_impl():
        called.append(True)
        return "should not run"
    registry = _registry_with([_tool("search", impl=watched_impl)])
    request = {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "search", "arguments": {"q": "secrets"}},
    }
    with patch("app.mcp.server.evaluate_composed", return_value=_block_decision()):
        response = dispatch(request, _ctx(), registry)
    result = response["result"]
    assert result["isError"] is True
    assert "Blocked by Guard rule" in result["content"][0]["text"]
    assert result["_blockedBy"] == "rule"
    assert result["_ruleId"] == "mcp.no_secret_search"
    assert not called  # tool impl never invoked


def test_tools_call_policy_eval_failure_fails_open():
    def impl():
        return "fallback"
    registry = _registry_with([_tool("thing", impl=impl)])
    request = {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "thing"},
    }
    with patch("app.mcp.server.evaluate_composed", side_effect=RuntimeError("db down")):
        response = dispatch(request, _ctx(), registry)
    result = response["result"]
    assert result["content"][0]["text"] == "fallback"
    assert "isError" not in result


def test_tools_call_impl_exception_returns_error_envelope():
    def impl():
        raise RuntimeError("something broke")
    registry = _registry_with([_tool("crashy", impl=impl)])
    request = {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "crashy"},
    }
    with patch("app.mcp.server.evaluate_composed", return_value=_allow_decision()):
        response = dispatch(request, _ctx(), registry)
    result = response["result"]
    assert result["isError"] is True
    assert "something broke" in result["content"][0]["text"]


def test_tools_call_impl_invalid_args_returns_error_envelope():
    def impl(required_arg):
        return "ok"
    registry = _registry_with([_tool("needs_arg", impl=impl)])
    request = {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "needs_arg", "arguments": {}},
    }
    with patch("app.mcp.server.evaluate_composed", return_value=_allow_decision()):
        response = dispatch(request, _ctx(), registry)
    result = response["result"]
    assert result["isError"] is True
    assert "Invalid arguments" in result["content"][0]["text"]


def test_tools_call_ctx_injection_when_impl_accepts_it():
    def impl(ctx, arg):
        return f"{ctx.workspace_id}:{arg}"
    registry = _registry_with([_tool("with_ctx", impl=impl)])
    request = {
        "jsonrpc": "2.0", "id": 3, "method": "tools/call",
        "params": {"name": "with_ctx", "arguments": {"arg": "hello"}},
    }
    with patch("app.mcp.server.evaluate_composed", return_value=_allow_decision()):
        response = dispatch(request, _ctx(), registry)
    text = response["result"]["content"][0]["text"]
    assert text.startswith("00000000-0000-0000-0000-000000000001")


# ─── unknown method ──────────────────────────────────────────────────────────

def test_unknown_method_returns_method_not_found():
    request = {"jsonrpc": "2.0", "id": 4, "method": "resources/list"}
    response = dispatch(request, _ctx(), ToolRegistry())
    assert response["error"]["code"] == -32601
    assert "resources/list" in response["error"]["message"]


# ─── new_session_id ──────────────────────────────────────────────────────────

def test_new_session_id_returns_valid_uuid():
    import uuid as _uuid
    sid = new_session_id()
    assert _uuid.UUID(sid)  # raises if not a valid UUID


def test_new_session_ids_are_unique():
    assert new_session_id() != new_session_id()
