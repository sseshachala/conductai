"""Unit tests for the layered-verdict envelope (#1150 phase 1).

Focuses on the pure engine slice — no DB, no HTTP. Exercises
_evaluate_policies via a stubbed compute_policy so we can control the
rule set precisely per test.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from app.modules.guard.routers import proxy as proxy_module
from app.modules.guard.routers.proxy import (
    SEVERITY_WEIGHTS,
    _defense_score,
    _evaluate_policies,
)


def _rule(
    rule_id: str,
    *,
    action: str = "warn",
    severity: str = "medium",
    match_prompt: str | None = None,
    match_pattern: str | None = None,
    match_provider: str | None = None,
    match_tool: str | None = None,
    message: str = "",
    non_overridable: bool = False,
) -> dict:
    r: dict = {
        "id": rule_id,
        "action": action,
        "severity": severity,
        "message": message or f"{rule_id} fired",
    }
    if match_prompt is not None:
        r["match_prompt"] = match_prompt
    if match_pattern is not None:
        r["match_pattern"] = match_pattern
    if match_provider is not None:
        r["match_provider"] = match_provider
    if match_tool is not None:
        r["match_tool"] = match_tool
    if non_overridable:
        r["non_overridable"] = True
    return r


def _stub_evaluate(rules: list[dict], *, body: dict | None = None, provider: str = "anthropic", model: str = "claude-3-5-sonnet"):
    """Run _evaluate_policies against a stubbed rule set."""
    body = body or {"messages": [{"role": "user", "content": "hello"}]}
    with patch.object(proxy_module, "compute_policy", return_value=rules), \
         patch.object(proxy_module, "set_workspace_rls"), \
         patch.object(proxy_module, "SessionLocal") as _sess, \
         patch.object(proxy_module, "_canonical_workspace_id", return_value="00000000-0000-0000-0000-000000000000"):
        _sess.return_value.close.return_value = None
        return _evaluate_policies("00000000-0000-0000-0000-000000000000", provider, model, body)


# --------------------------------------------------------------------------- #
# 1. Engine collects all matches (no short-circuit)
# --------------------------------------------------------------------------- #

def test_engine_evaluates_all_rules_no_short_circuit():
    rules = [
        _rule("r-block", action="block",  severity="critical", match_prompt="hello"),
        _rule("r-warn",  action="warn",   severity="high",     match_prompt="hello"),
        _rule("r-audit", action="audit",  severity="low",      match_prompt="hello"),
    ]
    v = _stub_evaluate(rules)
    ids = [m["rule_id"] for m in v["matched_rules"]]
    assert set(ids) == {"r-block", "r-warn", "r-audit"}


# --------------------------------------------------------------------------- #
# 2. Primary winner is the most restrictive matched action
# --------------------------------------------------------------------------- #

def test_primary_winner_is_most_restrictive_matched_rule():
    rules = [
        _rule("first-warn",   action="warn",  match_prompt="hello"),
        _rule("later-block",  action="block", match_prompt="hello"),  # later in list
        _rule("even-approval", action="approval", match_prompt="hello"),
    ]
    v = _stub_evaluate(rules)
    assert v["rule_id"] == "later-block"          # highest restrictiveness wins
    assert v["action"] == "BLOCK"


# --------------------------------------------------------------------------- #
# 3. evaluated_rules ordering — severity desc, then rule_id asc
# --------------------------------------------------------------------------- #

def test_evaluated_rules_ordering_deterministic():
    rules = [
        _rule("zzz-low",       action="audit", severity="low",      match_prompt="hello"),
        _rule("aaa-critical",  action="block", severity="critical", match_prompt="hello"),
        _rule("mmm-critical",  action="warn",  severity="critical", match_prompt="hello"),
        _rule("bbb-medium",    action="warn",  severity="medium",   match_prompt="hello"),
    ]
    v = _stub_evaluate(rules)
    order = [m["rule_id"] for m in v["matched_rules"]]
    # criticals first, tie broken by rule_id asc; medium; then low
    assert order == ["aaa-critical", "mmm-critical", "bbb-medium", "zzz-low"]


# --------------------------------------------------------------------------- #
# 4. Non-matched rules do not appear in matched_rules
# --------------------------------------------------------------------------- #

def test_matched_rules_contains_only_matches():
    rules = [
        _rule("match-me",  action="block", match_prompt="hello"),
        _rule("skip-me",   action="warn",  match_prompt="not-in-prompt"),
        _rule("skip-me-2", action="warn",  match_prompt="also-absent"),
    ]
    v = _stub_evaluate(rules)
    ids = [m["rule_id"] for m in v["matched_rules"]]
    assert ids == ["match-me"]


# --------------------------------------------------------------------------- #
# 5. defense_score aggregates severity weights across matched rules
# --------------------------------------------------------------------------- #

def test_defense_score_aggregates_severity_weights():
    rules = [
        _rule("a-crit",   action="block", severity="critical", match_prompt="hello"),  # 10
        _rule("b-high",   action="warn",  severity="high",     match_prompt="hello"),  # 5
        _rule("c-medium", action="warn",  severity="medium",   match_prompt="hello"),  # 3
        _rule("d-low",    action="audit", severity="low",      match_prompt="hello"),  # 1
    ]
    v = _stub_evaluate(rules)
    assert v["defense_score"] == 10 + 5 + 3 + 1


def test_defense_score_helper_handles_unknown_severity_as_medium():
    matched = [{"rule_id": "x", "severity": "unknown"}]
    assert _defense_score(matched) == SEVERITY_WEIGHTS["medium"]


# --------------------------------------------------------------------------- #
# 6. Zero matches — empty envelope, allow action
# --------------------------------------------------------------------------- #

def test_no_matches_produces_empty_envelope_and_allow():
    rules = [_rule("no-match", action="block", match_prompt="never-there")]
    v = _stub_evaluate(rules)
    assert v["action"] == "ALLOW"
    assert v["rule_id"] is None
    assert v["matched_rules"] == []
    assert v["defense_score"] == 0


# --------------------------------------------------------------------------- #
# 7. match_tool filter — hook-event rules (with match_tool) do not fire on proxy
# --------------------------------------------------------------------------- #

def test_hook_only_rules_excluded_from_proxy_eval():
    rules = [
        _rule("hook-rule", action="warn", match_pattern="hello", match_tool="bash"),
        _rule("proxy-rule", action="block", match_prompt="hello"),
    ]
    v = _stub_evaluate(rules)
    ids = [m["rule_id"] for m in v["matched_rules"]]
    assert ids == ["proxy-rule"]  # hook rule silently skipped


# --------------------------------------------------------------------------- #
# 8. match_provider filter — rules for a different provider are skipped
# --------------------------------------------------------------------------- #

def test_provider_filter_excludes_non_matching_provider_rules():
    rules = [
        _rule("only-openai",   action="block", match_provider="openai",    match_prompt="hello"),
        _rule("only-anthropic", action="block", match_provider="anthropic", match_prompt="hello"),
    ]
    v = _stub_evaluate(rules, provider="anthropic")
    ids = [m["rule_id"] for m in v["matched_rules"]]
    assert ids == ["only-anthropic"]


# --------------------------------------------------------------------------- #
# 9. Backward-compatible primary fields still present
# --------------------------------------------------------------------------- #

def test_primary_fields_present_and_populated():
    rules = [_rule("blocker", action="block", severity="high", match_prompt="hello", message="nope")]
    v = _stub_evaluate(rules)
    assert v["action"] == "BLOCK"
    assert v["rule_id"] == "blocker"
    assert v["message"] == "nope"
    assert "matched_rules" in v
    assert "defense_score" in v


# --------------------------------------------------------------------------- #
# 10. Winner rule spec exposed as decision["rule"] for downstream approval path
# --------------------------------------------------------------------------- #

def test_winner_full_rule_exposed_for_downstream_use():
    rules = [
        _rule("warn-rule",  action="warn",  match_prompt="hello"),
        _rule("block-rule", action="block", match_prompt="hello", message="stopped"),
    ]
    v = _stub_evaluate(rules)
    assert v["rule"]["id"] == "block-rule"        # winner full spec, not warn-rule


# --------------------------------------------------------------------------- #
# 11. Multiple rules with different actions on the same input — winner correct
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("actions,expected_action,expected_id", [
    (["audit", "warn"],           "WARN",     "warn"),
    (["warn", "approval"],        "APPROVAL", "approval"),
    (["approval", "block"],       "BLOCK",    "block"),
    (["allow", "audit", "warn"],  "WARN",     "warn"),
])
def test_winner_across_action_combinations(actions, expected_action, expected_id):
    rules = [_rule(a, action=a, match_prompt="hello") for a in actions]
    v = _stub_evaluate(rules)
    assert v["action"] == expected_action
    assert v["rule_id"] == expected_id
