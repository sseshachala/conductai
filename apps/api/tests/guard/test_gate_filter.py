"""#1733 PR 2 — gate-based rule filtering.

Locked enum: `[action, prompt, response]`. Every matcher (MCP + proxy)
consults `rule_matches_gate` before considering a rule. Default gate is
'action' for MCP callers, 'prompt' for proxy callers — chosen to match the
pre-#1733 evaluation semantics of each surface.
"""
from __future__ import annotations

from unittest.mock import patch

from app.modules.guard.enforcement import rule_matches_gate
from app.modules.guard.routers.mcp import _match_policy


def test_rule_matches_gate_uses_explicit_gates_field():
    rule = {"gates": ["prompt"]}
    assert rule_matches_gate(rule, "prompt") is True
    assert rule_matches_gate(rule, "action") is False
    assert rule_matches_gate(rule, "response") is False


def test_rule_matches_gate_derives_from_persona_when_gates_missing():
    """Legacy rule with only persona still resolves to a gate."""
    agent_rule = {"persona": "agent"}
    proxy_rule = {"persona": "proxy"}
    assert rule_matches_gate(agent_rule, "action") is True
    assert rule_matches_gate(agent_rule, "prompt") is False
    assert rule_matches_gate(proxy_rule, "prompt") is True
    assert rule_matches_gate(proxy_rule, "response") is False


def test_match_policy_default_gate_is_action():
    """Existing callers that don't pass a gate keep the MCP baseline."""
    action_rule = {
        "rule_id": "a",
        "match_tool": "bash",
        "action": "block",
        "gates": ["action"],
    }
    prompt_rule = {
        "rule_id": "p",
        "match_tool": "bash",
        "action": "block",
        "gates": ["prompt"],
    }
    hit = _match_policy("bash", {"command": "ls"}, [action_rule, prompt_rule])
    assert hit is not None
    assert hit["rule_id"] == "a"


def test_match_policy_prompt_gate_skips_action_rules():
    """When the caller says gate='prompt', pure action-gate rules must be filtered out."""
    action_rule = {
        "rule_id": "a",
        "match_tool": "bash",
        "action": "block",
        "gates": ["action"],
    }
    prompt_rule = {
        "rule_id": "p",
        "match_tool": "bash",
        "action": "block",
        "gates": ["prompt"],
    }
    hit = _match_policy(
        "bash", {"command": "ls"}, [action_rule, prompt_rule], gate="prompt"
    )
    assert hit is not None
    assert hit["rule_id"] == "p"


def test_match_policy_response_gate_returns_none_when_no_response_rules():
    action_rule = {
        "rule_id": "a",
        "match_tool": "bash",
        "action": "block",
        "gates": ["action"],
    }
    assert _match_policy("bash", {}, [action_rule], gate="response") is None


def test_match_policy_rule_with_multiple_gates_matches_any():
    dual_rule = {
        "rule_id": "d",
        "match_tool": "bash",
        "action": "block",
        "gates": ["action", "prompt"],
    }
    assert _match_policy("bash", {}, [dual_rule], gate="action")["rule_id"] == "d"
    assert _match_policy("bash", {}, [dual_rule], gate="prompt")["rule_id"] == "d"
    assert _match_policy("bash", {}, [dual_rule], gate="response") is None


def test_policy_context_default_gate_is_action():
    """PolicyContext defaults to gate='action' for callers that don't opt in."""
    from app.guard.policy_types import PolicyContext

    ctx = PolicyContext(workspace_id="ws", provider="anthropic", model="m", body={})
    assert ctx.gate == "action"


def test_policy_context_gate_can_be_set_to_prompt_or_response():
    from app.guard.policy_types import PolicyContext

    ctx = PolicyContext(
        workspace_id="ws", provider="anthropic", model="m", body={}, gate="response"
    )
    assert ctx.gate == "response"


def test_rule_policy_source_threads_ctx_gate_to_evaluator():
    """Composable engine → evaluate() must receive ctx.gate."""
    from app.guard.policy_types import PolicyContext
    from app.guard.sources import RulePolicySource

    seen = {}

    def _fake_evaluate(workspace_id, provider, model, body, gate="prompt", agent_risk_tier=None):
        seen["gate"] = gate
        return {"action": "ALLOW", "rule_id": None, "message": None}

    src = RulePolicySource(evaluator=_fake_evaluate)
    ctx = PolicyContext(
        workspace_id="ws", provider="anthropic", model="m", body={}, gate="response"
    )
    src.evaluate(ctx)
    assert seen["gate"] == "response"


def test_every_guarded_completion_call_site_labels_prompt_gate():
    """#1733 PR 3 — proxy egress call sites must label PolicyContext with
    gate='prompt' (or 'response' post-PR-4/5). Regression guard: every
    `_PolicyContext(` opening in the proxy files must be matched by a
    `gate=` line in the same file."""
    from pathlib import Path

    proxy_files = [
        Path(__file__).resolve().parents[2] / "app/guard/gateway.py",
        Path(__file__).resolve().parents[2] / "app/modules/guard/routers/proxy.py",
    ]
    for path in proxy_files:
        text = path.read_text()
        opens = text.count("_PolicyContext(")
        labels = text.count('gate="prompt"') + text.count('gate="response"')
        assert opens <= labels, (
            f"{path.name}: {opens} PolicyContext build sites, only {labels} "
            "gate labels. Every proxy-side _PolicyContext must set gate="
            "'prompt' or 'response' (#1733)."
        )
