"""#1733 / #1750 Phase A — derive_gates() from rule spec.

Locked enum: `[action, prompt, response]`. Legacy rules derive from persona;
explicit `gates` in the rule spec wins. Fallback is `[action]` — the safest
default because it matches pre-#1733 MCP behavior.
"""
from __future__ import annotations

from app.modules.guard.enforcement import GATES, derive_gates


def test_gates_enum_is_locked_to_three_values():
    assert GATES == ("action", "prompt", "response")


def test_derive_gates_defaults_to_action_and_prompt_when_persona_missing():
    """Empty rule inherits both personas (rule_personas returns {agent, proxy}
    when neither field is set), so it fires at both action + prompt."""
    assert derive_gates({}) == ["action", "prompt"]


def test_derive_gates_agent_persona_maps_to_action():
    assert derive_gates({"persona": "agent"}) == ["action"]


def test_derive_gates_proxy_persona_maps_to_prompt():
    assert derive_gates({"persona": "proxy"}) == ["prompt"]


def test_derive_gates_dual_persona_yields_both():
    assert derive_gates({"persona_affinity": ["agent", "proxy"]}) == ["action", "prompt"]


def test_explicit_gates_field_wins_over_persona():
    rule = {"persona": "agent", "gates": ["response"]}
    assert derive_gates(rule) == ["response"]


def test_explicit_gates_drops_unknown_values():
    """Reviewer edit 2: gates enum is locked. Unknown values are silently
    dropped rather than raising — legacy interop safety."""
    rule = {"gates": ["prompt", "hallucination-check", "response"]}
    assert derive_gates(rule) == ["prompt", "response"]


def test_explicit_gates_all_unknown_falls_back_to_persona():
    rule = {"gates": ["hallucination-check"], "persona": "proxy"}
    assert derive_gates(rule) == ["prompt"]


def test_derive_gates_preserves_action_prompt_response_order():
    rule = {"gates": ["response", "action", "prompt"]}
    assert derive_gates(rule) == ["action", "prompt", "response"]
