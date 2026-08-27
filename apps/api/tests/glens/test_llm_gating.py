"""#1254 — GLens Phase-1 (tool-select) LLM calls are policy-gated + audited.

Unit tests for `_gated_client_create`. Mocks `evaluate_composed` and
`record_audit` — no external LLM call, no DB row required.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _fake_decision(action_value: str, rule_id: str | None = None):
    """Build the minimal PolicyDecision shape the wrapper reads."""
    from app.guard.policy_types import PolicyAction
    return SimpleNamespace(
        action=PolicyAction[action_value],
        rule_id=rule_id,
        reason=None,
        matched_rules=[],
        defense_score=0,
    )


def _fake_executor():
    from unittest.mock import MagicMock as MM
    ex = MM()
    ex.workspace_id = "00000000-0000-0000-0000-000000000001"
    ex.db = None
    return ex


def test_allowed_call_records_audit_and_returns_response():
    from app.modules.glens.routers.chat import _gated_client_create

    client = MagicMock()
    client.create.return_value = SimpleNamespace(content=[])
    ex = _fake_executor()

    with patch("app.guard.policy.evaluate_composed", return_value=_fake_decision("ALLOW")) as ev, \
         patch("app.guard.audit.record") as rec:
        resp = _gated_client_create(client, ex, "openai", "gpt-4o-mini",
                                     messages=[{"role": "user", "content": "hi"}],
                                     system="sys", tools=[{"name": "get_event_count"}],
                                     max_tokens=512)

    assert resp is client.create.return_value
    client.create.assert_called_once()
    ev.assert_called_once()
    rec.assert_called_once()
    args, kwargs = rec.call_args
    assert args[2] == "lens", "ai_tool must be 'lens'"
    assert args[5] == "allowed", "decision must be 'allowed' when policy allows"
    assert kwargs.get("prompt_summary") == "lens.resolve_tools"


def test_blocked_call_records_blocked_row_and_raises():
    from app.modules.glens.routers.chat import _gated_client_create

    client = MagicMock()  # must not be called
    ex = _fake_executor()

    with patch("app.guard.policy.evaluate_composed",
               return_value=_fake_decision("BLOCK", rule_id="R-42")) as ev, \
         patch("app.guard.audit.record") as rec:
        with pytest.raises(Exception, match="Guard blocked Lens call"):
            _gated_client_create(client, ex, "openai", "gpt-4o-mini",
                                  messages=[{"role": "user", "content": "hi"}],
                                  system="sys", tools=[{"name": "get_event_count"}],
                                  max_tokens=512)

    client.create.assert_not_called()
    ev.assert_called_once()
    rec.assert_called_once()
    args, _ = rec.call_args
    assert args[5] == "blocked"
    assert args[6] == "R-42"


def test_warned_call_records_warned_and_still_returns():
    from app.modules.glens.routers.chat import _gated_client_create

    client = MagicMock()
    client.create.return_value = SimpleNamespace(content=[])
    ex = _fake_executor()

    with patch("app.guard.policy.evaluate_composed",
               return_value=_fake_decision("WARN", rule_id="R-warn")), \
         patch("app.guard.audit.record") as rec:
        _gated_client_create(client, ex, "openai", "gpt-4o-mini",
                              messages=[{"role": "user", "content": "hi"}],
                              system="sys", tools=[], max_tokens=512)

    client.create.assert_called_once()
    args, _ = rec.call_args
    assert args[5] == "warned"
    assert args[6] == "R-warn"
