"""Per-tool guard_check in the Lens dispatch path — #1218 Step 4, moved
from `Executor.call` to `app.mcp.lens_adapter.dispatch` in #1227.

Behaviour is unchanged: same error envelope, same policy path
(provider="lens"), same fail-open semantics. Post epic #1655, tool impls
are top-level free functions in `lens/<domain>.py` and the dispatcher
invokes `tool.impl(ctx, **args)` directly. Tests patch `tool.impl` on
the ToolDef instance to intercept.
"""
from __future__ import annotations

import json
from unittest.mock import patch, MagicMock

from app.guard.policy_types import PolicyAction, PolicyDecision
from app.mcp.lens_adapter import dispatch as lens_dispatch
from app.mcp.server import MCPContext
from app.tools import registrations  # noqa: F401  # side-effect: populate default_registry
from app.tools.registry import default_registry


_CTX = MCPContext(workspace_id="00000000-0000-0000-0000-000000000000", surface="lens")


def _patch_tool_impl(tool_name: str, **kwargs):
    """Patch a registered ToolDef.impl. Accepts the same kwargs as MagicMock
    (return_value, side_effect, etc.). Returns the patch context manager.
    """
    tool = default_registry.get(tool_name)
    assert tool is not None, f"tool not registered: {tool_name}"
    return patch.object(tool, "impl", MagicMock(**kwargs))


def test_dispatch_unknown_tool_short_circuits_before_guard():
    """Unknown tool returns error immediately — no guard eval needed."""
    with patch("app.mcp.lens_adapter.evaluate_composed") as mock_eval:
        result = lens_dispatch("nonexistent_tool", "{}", _CTX)
    assert "Unknown tool" in result
    assert not mock_eval.called


def test_dispatch_allowed_tool_runs_normally():
    allow_decision = PolicyDecision(action=PolicyAction.ALLOW, source="rule")
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=allow_decision), \
         _patch_tool_impl("get_spend_summary", return_value={"ok": True}):
        result = lens_dispatch("get_spend_summary", "{}", _CTX)
    assert json.loads(result) == {"ok": True}


def test_dispatch_blocked_tool_returns_error_envelope():
    block_decision = PolicyDecision(
        action=PolicyAction.BLOCK,
        source="rule",
        rule_id="lens.no_secrets_search",
        reason="Blocked search for secrets",
    )
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=block_decision), \
         _patch_tool_impl("search_knowledge") as mock_tool_ctx:
        result = lens_dispatch("search_knowledge", '{"q": "aws_secret_key"}', _CTX)
        # We need the mock reference for .called; grab it from the tool
        tool = default_registry.get("search_knowledge")
        assert not tool.impl.called
    parsed = json.loads(result)
    assert "Blocked by Guard rule" in parsed["error"]
    assert parsed["blocked_by"] == "rule"
    assert parsed["rule_id"] == "lens.no_secrets_search"


def test_dispatch_guard_check_failure_fails_open():
    """If the composable engine itself crashes, we fail-open (log + proceed)
    so a broken policy source can't lock Lens out of all tools."""
    with patch("app.mcp.lens_adapter.evaluate_composed",
               side_effect=RuntimeError("db down")), \
         _patch_tool_impl("get_spend_summary", return_value={"fallback": True}):
        result = lens_dispatch("get_spend_summary", "{}", _CTX)
    assert json.loads(result) == {"fallback": True}


def test_dispatch_tool_exception_returns_error_envelope():
    """Tool implementation raises — adapter catches + returns error dict."""
    allow_decision = PolicyDecision(action=PolicyAction.ALLOW, source="rule")
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=allow_decision), \
         _patch_tool_impl("get_spend_summary", side_effect=RuntimeError("boom")):
        result = lens_dispatch("get_spend_summary", "{}", _CTX)
    parsed = json.loads(result)
    assert parsed["error"] == "boom"


def test_dispatch_arguments_passed_to_tool():
    allow_decision = PolicyDecision(action=PolicyAction.ALLOW, source="rule")
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=allow_decision), \
         _patch_tool_impl("get_spend_summary", return_value={"month": "2026-08"}):
        result = lens_dispatch("get_spend_summary", '{"month": "2026-08"}', _CTX)
        tool = default_registry.get("get_spend_summary")
        tool.impl.assert_called_once_with(_CTX, month="2026-08")
    assert json.loads(result) == {"month": "2026-08"}


def test_dispatch_context_shape_for_tool_policy_eval():
    """PolicyContext passed to composable engine should identify the tool
    call — enables rules that target specific tools or arg patterns."""
    allow_decision = PolicyDecision(action=PolicyAction.ALLOW, source="rule")
    captured_ctx = []

    def _capture(ctx):
        captured_ctx.append(ctx)
        return allow_decision

    with patch("app.mcp.lens_adapter.evaluate_composed", side_effect=_capture), \
         _patch_tool_impl("search_memory", return_value={"hits": []}):
        lens_dispatch("search_memory", '{"q": "hello"}', _CTX)

    assert len(captured_ctx) == 1
    ctx = captured_ctx[0]
    assert ctx.provider == "lens"
    assert ctx.model == "tool"
    assert ctx.body["tool_name"] == "search_memory"
    assert ctx.body["arguments"] == {"q": "hello"}
    assert ctx.extras["kind"] == "lens_tool"
    assert ctx.extras["tool_name"] == "search_memory"
