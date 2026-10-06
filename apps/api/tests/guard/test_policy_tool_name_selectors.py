"""Tool-name selectors through the matcher and composed engine (#2156)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.guard import policy
from app.guard.policy import _is_proxy_rule, _rule_matches, evaluate_composed
from app.guard.policy_types import PolicyAction, PolicyContext
from app.guard.sources import RulePolicySource
from app.modules.guard.tools_validator import extract_tool_names_supplied


class TestIsProxyRuleRecognizesToolNameKeys:
    def test_tool_name_offered_is_proxy_rule(self) -> None:
        assert _is_proxy_rule({"match_tool_name_offered": "send_email"})

    def test_tool_name_generated_is_proxy_rule(self) -> None:
        assert _is_proxy_rule({"match_tool_name_generated": "shell_exec"})

    def test_tool_name_supplied_is_proxy_rule(self) -> None:
        assert _is_proxy_rule({"match_tool_name_supplied": "bank_transfer"})

    def test_rule_without_any_matcher_is_not_proxy_rule(self) -> None:
        assert not _is_proxy_rule({"action": "block"})


class TestMatchToolNameOffered:
    def test_matches_when_pattern_hits_offered_list(self) -> None:
        rule = {"match_tool_name_offered": "send_email"}
        assert _rule_matches(
            rule, "openai", "gpt-4o", "prompt text",
            tool_names_offered=["get_weather", "send_email"],
        )

    def test_no_match_when_pattern_misses(self) -> None:
        rule = {"match_tool_name_offered": "shell_exec"}
        assert not _rule_matches(
            rule, "openai", "gpt-4o", "prompt text",
            tool_names_offered=["get_weather", "send_email"],
        )

    def test_no_match_when_offered_list_unset(self) -> None:
        # Rule requires a signal that PEP didn't populate → cannot fire.
        # This is the safe default per the epic (match_agent_risk_tier
        # follows the same rule).
        rule = {"match_tool_name_offered": "send_email"}
        assert not _rule_matches(
            rule, "openai", "gpt-4o", "prompt text",
            tool_names_offered=None,
        )

    def test_no_match_when_offered_list_empty(self) -> None:
        rule = {"match_tool_name_offered": "send_email"}
        assert not _rule_matches(
            rule, "openai", "gpt-4o", "prompt text",
            tool_names_offered=[],
        )

    def test_regex_pattern_case_insensitive(self) -> None:
        rule = {"match_tool_name_offered": "^SEND_"}
        assert _rule_matches(
            rule, "openai", "gpt-4o", "prompt text",
            tool_names_offered=["send_email"],
        )


class TestMatchToolNameGenerated:
    def test_matches_when_model_returned_matching_tool(self) -> None:
        rule = {"match_tool_name_generated": "shell_exec"}
        assert _rule_matches(
            rule, "openai", "gpt-4o", "",
            tool_names_generated=["shell_exec"],
        )

    def test_no_match_when_model_returned_different_tool(self) -> None:
        rule = {"match_tool_name_generated": "shell_exec"}
        assert not _rule_matches(
            rule, "openai", "gpt-4o", "",
            tool_names_generated=["get_weather"],
        )


class TestMatchToolNameSupplied:
    def test_matches_when_caller_supplied_result_for_named_tool(self) -> None:
        rule = {"match_tool_name_supplied": "bank_transfer"}
        assert _rule_matches(
            rule, "openai", "gpt-4o", "",
            tool_names_supplied=["bank_transfer", "send_email"],
        )


class TestCombinedMatchers:
    def test_provider_and_tool_name_both_required(self) -> None:
        # Rule combines match_provider + match_tool_name_offered — must
        # fire only when BOTH conditions hit.
        rule = {
            "match_provider": "openai",
            "match_tool_name_offered": "send_email",
        }
        # Both hit → match.
        assert _rule_matches(
            rule, "openai", "gpt-4o", "",
            tool_names_offered=["send_email"],
        )
        # Wrong provider → no match even though tool matches.
        assert not _rule_matches(
            rule, "anthropic", "claude-3", "",
            tool_names_offered=["send_email"],
        )
        # Right provider, wrong tool → no match.
        assert not _rule_matches(
            rule, "openai", "gpt-4o", "",
            tool_names_offered=["get_weather"],
        )

    def test_rule_without_any_tool_matcher_unaffected(self) -> None:
        # Pre-#2156 rules keep working — the tool_names_* args default
        # to None and are only checked when the rule opts in.
        rule = {"match_provider": "openai", "match_prompt": "hello"}
        assert _rule_matches(
            rule, "openai", "gpt-4o", "hello world",
        )
        # Populating tool_names_* on a rule that doesn't reference them
        # is a no-op.
        assert _rule_matches(
            rule, "openai", "gpt-4o", "hello world",
            tool_names_offered=["anything", "at", "all"],
        )


@pytest.fixture
def policy_snapshot(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    # Stub storage only; exercise the real source, evaluator, and matcher.
    rules: list[dict] = []
    session = MagicMock()
    monkeypatch.setattr(policy, "SessionLocal", lambda: session)
    monkeypatch.setattr(policy, "_canonical_workspace_id", lambda workspace: workspace)
    monkeypatch.setattr(policy, "set_workspace_rls", lambda db, workspace: None)
    monkeypatch.setattr(policy, "compute_policy", lambda db, workspace, surface: rules)
    return rules


_TOOL_SIGNALS = [
    ("offered", "prompt"),
    ("generated", "response"),
    ("supplied", "prompt"),
]


def _context(gate: str = "prompt", **signals) -> PolicyContext:
    return PolicyContext(
        workspace_id="00000000-0000-0000-0000-000000000001",
        provider="openai",
        model="gpt-4o",
        body={"messages": []},
        gate=gate,
        **signals,
    )


@pytest.mark.parametrize("signal,gate", _TOOL_SIGNALS)
@pytest.mark.parametrize("action", [PolicyAction.BLOCK, PolicyAction.WARN, PolicyAction.APPROVAL])
def test_composed_engine_applies_tool_name_selector(policy_snapshot, signal, gate, action):
    policy_snapshot.append({
        "id": "tool-name-rule",
        "gates": [gate],
        f"match_tool_name_{signal}": "^bank_transfer$",
        "action": action.value.lower(),
    })
    ctx = _context(gate, **{f"tool_names_{signal}": ["bank_transfer"]})

    decision = evaluate_composed(ctx, sources=[RulePolicySource()])

    assert decision.action == action
    assert decision.rule_id == "tool-name-rule"
    assert decision.matched_rules[0]["rule_id"] == "tool-name-rule"


@pytest.mark.parametrize("signal,gate", _TOOL_SIGNALS)
@pytest.mark.parametrize("names", [None, []])
def test_composed_engine_missing_tool_signal_does_not_match(policy_snapshot, signal, gate, names):
    policy_snapshot.append({
        "id": "tool-name-rule",
        "gates": [gate],
        f"match_tool_name_{signal}": "bank_transfer",
        "action": "block",
    })
    ctx = _context(gate, **{f"tool_names_{signal}": names})

    decision = evaluate_composed(ctx, sources=[RulePolicySource()])

    assert decision.action == PolicyAction.ALLOW
    assert decision.matched_rules == []


@pytest.mark.parametrize("pattern,expected", [
    ("^bank_transfer$", PolicyAction.BLOCK),
    ("^call_abc$", PolicyAction.ALLOW),
])
def test_supplied_result_resolves_name_before_composed_evaluation(policy_snapshot, pattern, expected):
    body = {"messages": [
        {"role": "assistant", "tool_calls": [{
            "id": "call_abc",
            "type": "function",
            "function": {"name": "bank_transfer", "arguments": "{}"},
        }]},
        {"role": "tool", "tool_call_id": "call_abc", "content": "ok"},
    ]}
    names = extract_tool_names_supplied(body)
    assert names == ["bank_transfer"]
    policy_snapshot.append({
        "id": "supplied-tool-rule",
        "gates": ["prompt"],
        "match_tool_name_supplied": pattern,
        "action": "block",
    })
    ctx = _context(tool_names_supplied=names)
    ctx.body = body

    decision = evaluate_composed(ctx, sources=[RulePolicySource()])

    assert decision.action == expected


def test_orphan_tool_result_does_not_match_name_selector(policy_snapshot):
    body = {"messages": [
        {"role": "tool", "tool_call_id": "bank_transfer", "content": "ok"},
    ]}
    names = extract_tool_names_supplied(body)
    assert names == []
    policy_snapshot.append({
        "id": "supplied-tool-rule",
        "gates": ["prompt"],
        "match_tool_name_supplied": "bank_transfer",
        "action": "block",
    })

    decision = evaluate_composed(_context(tool_names_supplied=names), sources=[RulePolicySource()])

    assert decision.action == PolicyAction.ALLOW


def test_composed_engine_existing_rule_is_unchanged(policy_snapshot):
    policy_snapshot.append({
        "id": "existing-provider-rule",
        "gates": ["prompt"],
        "match_provider": "openai",
        "action": "warn",
    })
    ctx = _context(
        tool_names_offered=["bank_transfer"],
        tool_names_generated=["send_email"],
        tool_names_supplied=["get_weather"],
    )

    decision = evaluate_composed(ctx, sources=[RulePolicySource()])

    assert decision.action == PolicyAction.WARN
    assert decision.rule_id == "existing-provider-rule"
