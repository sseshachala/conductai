"""Per-tool guard_check in the Lens dispatch path — #1218 Step 4, moved
from `Executor.call` to `app.mcp.lens_adapter.dispatch` in #1227.

Behaviour is unchanged: same error envelope, same policy path
(provider="lens"), same fail-open semantics. Tool impls still live on
Executor as `_tool_*` methods; the registry projects them via
`_impl(method_name)` in `app/tools/registrations/lens.py`.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from app.guard.policy_types import PolicyAction, PolicyDecision
from app.mcp.lens_adapter import dispatch as lens_dispatch
from app.mcp.server import MCPContext
from app.tools import registrations  # noqa: F401  # side-effect: populate default_registry


_CTX = MCPContext(workspace_id="00000000-0000-0000-0000-000000000000", surface="lens")


def test_dispatch_unknown_tool_short_circuits_before_guard():
    """Unknown tool returns error immediately — no guard eval needed."""
    with patch("app.mcp.lens_adapter.evaluate_composed") as mock_eval:
        result = lens_dispatch("nonexistent_tool", "{}", _CTX)
    assert "Unknown tool" in result
    assert not mock_eval.called


def test_dispatch_allowed_tool_runs_normally():
    allow_decision = PolicyDecision(action=PolicyAction.ALLOW, source="rule")
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=allow_decision), \
         patch("app.modules.glens.executor.Executor._tool_get_spend_summary",
               return_value={"ok": True}, create=True):
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
         patch("app.modules.glens.executor.Executor._tool_search_knowledge",
               create=True) as mock_tool:
        result = lens_dispatch("search_knowledge", '{"q": "aws_secret_key"}', _CTX)
    parsed = json.loads(result)
    assert "Blocked by Guard rule" in parsed["error"]
    assert parsed["blocked_by"] == "rule"
    assert parsed["rule_id"] == "lens.no_secrets_search"
    # Tool implementation must NOT be called when policy blocks
    assert not mock_tool.called


def test_dispatch_guard_check_failure_fails_open():
    """If the composable engine itself crashes, we fail-open (log + proceed)
    so a broken policy source can't lock Lens out of all tools."""
    with patch("app.mcp.lens_adapter.evaluate_composed",
               side_effect=RuntimeError("db down")), \
         patch("app.modules.glens.executor.Executor._tool_get_spend_summary",
               return_value={"fallback": True}, create=True):
        result = lens_dispatch("get_spend_summary", "{}", _CTX)
    assert json.loads(result) == {"fallback": True}


def test_dispatch_tool_exception_returns_error_envelope():
    """Tool implementation raises — adapter catches + returns error dict."""
    allow_decision = PolicyDecision(action=PolicyAction.ALLOW, source="rule")
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=allow_decision), \
         patch("app.modules.glens.executor.Executor._tool_get_spend_summary",
               side_effect=RuntimeError("boom"), create=True):
        result = lens_dispatch("get_spend_summary", "{}", _CTX)
    parsed = json.loads(result)
    assert parsed["error"] == "boom"


def test_dispatch_arguments_passed_to_tool():
    allow_decision = PolicyDecision(action=PolicyAction.ALLOW, source="rule")
    with patch("app.mcp.lens_adapter.evaluate_composed", return_value=allow_decision), \
         patch("app.modules.glens.executor.Executor._tool_get_spend_summary",
               return_value={"month": "2026-08"}, create=True) as mock_tool:
        result = lens_dispatch("get_spend_summary", '{"month": "2026-08"}', _CTX)
    assert json.loads(result) == {"month": "2026-08"}
    mock_tool.assert_called_once_with(month="2026-08")


def test_dispatch_context_shape_for_tool_policy_eval():
    """PolicyContext passed to composable engine should identify the tool
    call — enables rules that target specific tools or arg patterns."""
    allow_decision = PolicyDecision(action=PolicyAction.ALLOW, source="rule")
    captured_ctx = []

    def _capture(ctx):
        captured_ctx.append(ctx)
        return allow_decision

    with patch("app.mcp.lens_adapter.evaluate_composed", side_effect=_capture), \
         patch("app.modules.glens.executor.Executor._tool_search_memory",
               return_value={"hits": []}, create=True):
        lens_dispatch("search_memory", '{"q": "hello"}', _CTX)

    assert len(captured_ctx) == 1
    ctx = captured_ctx[0]
    assert ctx.provider == "lens"
    assert ctx.model == "tool"
    assert ctx.body["tool_name"] == "search_memory"
    assert ctx.body["arguments"] == {"q": "hello"}
    assert ctx.extras["kind"] == "lens_tool"
    assert ctx.extras["tool_name"] == "search_memory"
