"""Per-tool guard_check in Executor.call() — #1218 Step 4."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.guard.policy_types import PolicyAction, PolicyDecision
from app.modules.glens.executor import Executor


def _executor():
    return Executor(db=MagicMock(), workspace_id="00000000-0000-0000-0000-000000000000")


def test_call_unknown_tool_short_circuits_before_guard():
    """Unknown tool returns error immediately — no guard eval needed."""
    ex = _executor()
    with patch("app.guard.policy.evaluate_composed") as mock_eval:
        result = ex.call("nonexistent_tool", "{}")
    assert "Unknown tool" in result
    assert not mock_eval.called


def test_call_allowed_tool_runs_normally():
    ex = _executor()
    allow_decision = PolicyDecision(action=PolicyAction.ALLOW, source="rule")
    with patch("app.guard.policy.evaluate_composed", return_value=allow_decision), \
         patch.object(ex, "_tool_get_spend_summary", return_value={"ok": True}):
        result = ex.call("get_spend_summary", "{}")
    assert json.loads(result) == {"ok": True}


def test_call_blocked_tool_returns_error_envelope():
    ex = _executor()
    block_decision = PolicyDecision(
        action=PolicyAction.BLOCK,
        source="rule",
        rule_id="lens.no_secrets_search",
        reason="Blocked search for secrets",
    )
    with patch("app.guard.policy.evaluate_composed", return_value=block_decision), \
         patch.object(ex, "_tool_search_knowledge") as mock_tool:
        result = ex.call("search_knowledge", '{"q": "aws_secret_key"}')
    parsed = json.loads(result)
    assert "Blocked by Guard rule" in parsed["error"]
    assert parsed["blocked_by"] == "rule"
    assert parsed["rule_id"] == "lens.no_secrets_search"
    # Tool implementation must NOT be called when policy blocks
    assert not mock_tool.called


def test_call_guard_check_failure_fails_open():
    """If the composable engine itself crashes, we fail-open (log + proceed)
    so a broken policy source can't lock Lens out of all tools."""
    ex = _executor()
    with patch("app.guard.policy.evaluate_composed", side_effect=RuntimeError("db down")), \
         patch.object(ex, "_tool_get_spend_summary", return_value={"fallback": True}):
        result = ex.call("get_spend_summary", "{}")
    assert json.loads(result) == {"fallback": True}


def test_call_tool_exception_returns_error_envelope():
    """Tool implementation raises — Executor catches + returns error dict."""
    ex = _executor()
    allow_decision = PolicyDecision(action=PolicyAction.ALLOW, source="rule")
    with patch("app.guard.policy.evaluate_composed", return_value=allow_decision), \
         patch.object(ex, "_tool_get_spend_summary", side_effect=RuntimeError("boom")):
        result = ex.call("get_spend_summary", "{}")
    parsed = json.loads(result)
    assert parsed["error"] == "boom"


def test_call_arguments_passed_to_tool():
    ex = _executor()
    allow_decision = PolicyDecision(action=PolicyAction.ALLOW, source="rule")
    with patch("app.guard.policy.evaluate_composed", return_value=allow_decision), \
         patch.object(ex, "_tool_get_spend_summary", return_value={"month": "2026-08"}) as mock_tool:
        result = ex.call("get_spend_summary", '{"month": "2026-08"}')
    assert json.loads(result) == {"month": "2026-08"}
    mock_tool.assert_called_once_with(month="2026-08")


def test_call_context_shape_for_tool_policy_eval():
    """PolicyContext passed to composable engine should identify the tool
    call — enables rules that target specific tools or arg patterns."""
    ex = _executor()
    allow_decision = PolicyDecision(action=PolicyAction.ALLOW, source="rule")
    captured_ctx = []

    def _capture(ctx):
        captured_ctx.append(ctx)
        return allow_decision

    with patch("app.guard.policy.evaluate_composed", side_effect=_capture), \
         patch.object(ex, "_tool_search_memory", return_value={"hits": []}):
        ex.call("search_memory", '{"q": "hello"}')

    assert len(captured_ctx) == 1
    ctx = captured_ctx[0]
    assert ctx.provider == "lens"
    assert ctx.model == "tool"
    assert ctx.body["tool_name"] == "search_memory"
    assert ctx.body["arguments"] == {"q": "hello"}
    assert ctx.extras["kind"] == "lens_tool"
    assert ctx.extras["tool_name"] == "search_memory"
