"""Composed-engine tests for tool_name selectors (#2156).

Proves that the three ``match_tool_name_*`` rule keys actually flow
through ``_rule_matches`` when the PEP populates the PolicyContext with
tool-name lists.

These tests exercise ``_rule_matches`` directly rather than the full
``evaluate()`` path — that path needs a workspace + policy-snapshot
DB, which is integration-only. The unit-level matcher is where the
selector logic lives, so testing it here covers the semantic contract.
"""
from __future__ import annotations

import pytest

from app.guard.policy import _is_proxy_rule, _rule_matches


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
        # tool_names_supplied is a list of tool_call_ids (not names). The
        # rule matches on the ID string — this is by design; the caller
        # decides ID scheme. Pattern here is contains "call_abc".
        rule = {"match_tool_name_supplied": "call_abc"}
        assert _rule_matches(
            rule, "openai", "gpt-4o", "",
            tool_names_supplied=["call_abc", "call_xyz"],
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
