"""Fix 4 (P1 #4) — transport-scoped caps actually enforce.

Reviewer P1 #4. Pre-fix, an admin who saved a budget row with
``ai_tool='gateway'`` (via the transport optgroup in the UI added by
#2096) saw the row persist but never fire: ``SpendCapPolicySource``
passed the client tool string (e.g., ``'cursor'``) to ``budget_check``
and never matched the gateway-labelled row.

Post-fix: SpendCapPolicySource infers the transport from ``ctx.gate``
(``'prompt'`` / ``'response'`` -> gateway, ``'action'`` -> mcp) and
forwards it to ``budget_check(transport=...)``. The check aggregates
events with ``source=<transport>`` against the matching budget row's
hard limit and blocks when the pool is over.

Tests here exercise the SpendCapPolicySource + budget_check contract
via mocks; the real DB path is covered by existing spend tests.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.guard.policy_types import PolicyAction, PolicyContext
from app.guard.sources import SpendCapPolicySource


def _ctx(gate: str, ai_tool: str | None = "cursor"):
    return PolicyContext(
        workspace_id="00000000-0000-0000-0000-000000000000",
        provider="anthropic",
        model="claude-3-5-sonnet",
        body={"messages": []},
        clerk_user_id="user-1",
        ai_tool=ai_tool,
        db=MagicMock(),
        gate=gate,
    )


def _make_checker(hard_blocked: bool = False):
    """Returns a checker fake that records the transport arg."""
    calls = []

    def _checker(*, workspace_id, clerk_user_id, ai_tool, transport, db):
        calls.append({
            "workspace_id": workspace_id,
            "clerk_user_id": clerk_user_id,
            "ai_tool": ai_tool,
            "transport": transport,
        })
        return _CheckerReturn(hard_blocked)

    _checker.calls = calls
    return _checker


class _CheckerReturn:
    def __init__(self, hard_blocked):
        self.hard_blocked = hard_blocked
        self.monthly_cost_usd = 0.0
        self.hard_limit_usd = None
        self.reason = "over budget" if hard_blocked else None


def test_prompt_gate_forwards_transport_gateway():
    """Egress LLM proxy path -> transport='gateway'."""
    checker = _make_checker()
    source = SpendCapPolicySource(checker=checker)
    source.evaluate(_ctx(gate="prompt"))
    assert checker.calls[0]["transport"] == "gateway"


def test_response_gate_forwards_transport_gateway():
    """Ingress LLM proxy path (response gate) -> transport='gateway'."""
    checker = _make_checker()
    source = SpendCapPolicySource(checker=checker)
    source.evaluate(_ctx(gate="response"))
    assert checker.calls[0]["transport"] == "gateway"


def test_action_gate_forwards_transport_mcp():
    """MCP tool call -> transport='mcp'."""
    checker = _make_checker()
    source = SpendCapPolicySource(checker=checker)
    source.evaluate(_ctx(gate="action"))
    assert checker.calls[0]["transport"] == "mcp"


def test_transport_scope_does_not_clobber_client_tool():
    """Both dimensions co-exist: client tool ('cursor') and transport
    ('gateway') are independent budget scopes."""
    checker = _make_checker()
    source = SpendCapPolicySource(checker=checker)
    source.evaluate(_ctx(gate="prompt", ai_tool="cursor"))
    call = checker.calls[0]
    assert call["ai_tool"] == "cursor"
    assert call["transport"] == "gateway"


def test_hard_block_from_transport_still_returns_block_decision():
    """If budget_check reports hard_blocked=True on a transport-scoped
    row, the policy source still returns BLOCK — no special-case for
    transport vs tool caps."""
    checker = _make_checker(hard_blocked=True)
    source = SpendCapPolicySource(checker=checker)
    decision = source.evaluate(_ctx(gate="prompt"))
    assert decision.action is PolicyAction.BLOCK
