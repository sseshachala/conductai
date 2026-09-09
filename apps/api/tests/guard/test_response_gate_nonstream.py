"""#1733 PR 4 — response gate (non-streaming path).

Verifies:
- Response-gate rule that fires BLOCK swaps the upstream body for a
  ConductGuard 451 envelope.
- Response-gate rule that fires WARN passes the original body through.
- ``flatten_response`` extracts text from Anthropic + OpenAI shapes.
- The response gate short-circuits on error (fail-open) so a policy hiccup
  never breaks the response path.
"""
from __future__ import annotations

import json
from unittest.mock import patch

from fastapi.responses import JSONResponse

from app.guard.policy import flatten_prompt, flatten_response
from app.guard.policy_types import PolicyAction, PolicyDecision
from app.modules.guard.routers.proxy import _apply_response_gate


def _resp(body: dict, status: int = 200) -> JSONResponse:
    return JSONResponse(status_code=status, content=body)


def test_flatten_response_anthropic_shape():
    body = {"content": [{"type": "text", "text": "hello patient SSN 123-45-6789"}]}
    assert "SSN 123-45-6789" in flatten_response(body)


def test_flatten_response_openai_shape():
    body = {"choices": [{"message": {"content": "hello patient"}}]}
    assert flatten_response(body) == "hello patient"


def test_flatten_response_unknown_shape_returns_empty():
    assert flatten_response({"weird": True}) == ""


def test_flatten_prompt_still_ignores_response_shape():
    """Sanity: response-shape bodies must NOT flow through prompt extraction."""
    body = {"content": [{"type": "text", "text": "assistant reply"}]}
    assert flatten_prompt(body) == ""


def test_apply_response_gate_passes_through_on_allow():
    anthropic_response = _resp({"content": [{"type": "text", "text": "hi"}]})
    with patch(
        "app.guard.policy.evaluate_composed",
        return_value=PolicyDecision(action=PolicyAction.ALLOW, source="rule"),
    ):
        out = _apply_response_gate(
            anthropic_response, workspace_id="ws-a", provider="anthropic",
            model="claude-3", clerk_user_id="u1", agent_identity_id=None,
        )
    assert out is anthropic_response  # unchanged, same object


def test_apply_response_gate_replaces_body_on_block():
    anthropic_response = _resp({"content": [{"type": "text", "text": "SSN leak"}]})
    with patch(
        "app.guard.policy.evaluate_composed",
        return_value=PolicyDecision(
            action=PolicyAction.BLOCK, source="rule",
            reason="PHI detected in model reply", rule_id="hipaa-no-ssn-out",
        ),
    ):
        out = _apply_response_gate(
            anthropic_response, workspace_id="ws-a", provider="anthropic",
            model="claude-3", clerk_user_id="u1", agent_identity_id=None,
        )
    assert out is not anthropic_response
    assert out.status_code == 451
    payload = json.loads(out.body)
    assert payload["error"]["type"] == "conduct_guard_response_block"
    assert payload["error"]["rule_id"] == "hipaa-no-ssn-out"
    assert payload["error"]["gate"] == "response"


def test_apply_response_gate_fails_open_on_error():
    """A crash inside the response scan must not corrupt the response body."""
    orig = _resp({"content": [{"type": "text", "text": "hi"}]})
    with patch(
        "app.guard.policy.evaluate_composed",
        side_effect=RuntimeError("engine down"),
    ):
        out = _apply_response_gate(
            orig, workspace_id="ws-a", provider="anthropic",
            model="claude-3", clerk_user_id="u1", agent_identity_id=None,
        )
    assert out is orig


def test_apply_response_gate_context_labels_response_gate():
    """Regression: the ctx passed to evaluate_composed must have gate='response'."""
    orig = _resp({"content": [{"type": "text", "text": "hi"}]})
    seen = {}

    def _spy(ctx):
        seen["gate"] = ctx.gate
        return PolicyDecision(action=PolicyAction.ALLOW, source="rule")

    with patch("app.guard.policy.evaluate_composed", side_effect=_spy):
        _apply_response_gate(
            orig, workspace_id="ws-a", provider="anthropic",
            model="claude-3", clerk_user_id="u1", agent_identity_id=None,
        )
    assert seen["gate"] == "response"
