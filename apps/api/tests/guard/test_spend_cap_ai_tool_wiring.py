"""Verify SpendCapPolicySource threads PolicyContext.ai_tool into budget_check.

Companion to test_spend_budget_check.py (which covers the endpoint's own
per-tool logic). This test locks the wiring: setting ctx.ai_tool must
change what SpendCap asks the budget checker; the "unknown" sentinel must
be normalized to None so per-tool rows don't match on a placeholder.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.guard.sources import SpendCapPolicySource
from app.guard.policy_types import PolicyContext, PolicyAction


def _ctx(ai_tool):
    return PolicyContext(
        workspace_id="ef0a7e36-42a7-4968-9e6f-ee30d8e45383",
        clerk_user_id="user_abc",
        provider="anthropic",
        model="claude-sonnet-4-5",
        body={},
        db=MagicMock(),
        ai_tool=ai_tool,
    )


def _stub_checker(hard_blocked=False, reason=None, monthly_cost_usd=0.0, hard_limit_usd=None):
    """Return a callable that records its kwargs on `.last_kwargs`."""
    def _check(**kwargs):
        _check.last_kwargs = kwargs
        return SimpleNamespace(
            hard_blocked=hard_blocked,
            reason=reason,
            monthly_cost_usd=monthly_cost_usd,
            hard_limit_usd=hard_limit_usd,
        )
    _check.last_kwargs = {}
    return _check


def test_ai_tool_is_forwarded_to_budget_check():
    checker = _stub_checker()
    source = SpendCapPolicySource(checker=checker)
    source.evaluate(_ctx(ai_tool="codex-desktop"))
    assert checker.last_kwargs.get("ai_tool") == "codex-desktop"


def test_none_ai_tool_forwarded_as_none():
    checker = _stub_checker()
    source = SpendCapPolicySource(checker=checker)
    source.evaluate(_ctx(ai_tool=None))
    assert checker.last_kwargs.get("ai_tool") is None


def test_unknown_ai_tool_normalized_to_none():
    """'unknown' is the sentinel emitted by detect_ai_tool when it cannot
    identify the client. SpendCap must treat it as absence — otherwise
    every unidentified client would collide on a phantom 'unknown' bucket
    that no legitimate config would ever set up."""
    checker = _stub_checker()
    source = SpendCapPolicySource(checker=checker)
    source.evaluate(_ctx(ai_tool="unknown"))
    assert checker.last_kwargs.get("ai_tool") is None


def test_hard_blocked_shape_still_returns_block():
    """Belt-and-braces — the outer decision path is untouched by the
    ai_tool threading."""
    checker = _stub_checker(hard_blocked=True, reason="over cap", monthly_cost_usd=100.0, hard_limit_usd=50.0)
    source = SpendCapPolicySource(checker=checker)
    decision = source.evaluate(_ctx(ai_tool="codex-desktop"))
    assert decision.action == PolicyAction.BLOCK
    assert decision.reason == "over cap"
