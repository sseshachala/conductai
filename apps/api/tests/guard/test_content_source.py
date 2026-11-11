"""match_content_source: per-source scanning of tool results / tool descriptions (#2384).

Uses a synthetic marker pattern so the tests exercise the selector mechanism,
not any real injection payload.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.guard import policy
from app.guard.policy import (
    _is_proxy_rule,
    _rule_matches,
    evaluate_composed,
    flatten_prompt,
    flatten_tool_descriptions,
    flatten_tool_results,
    rule_content_sources,
)
from app.guard.policy_types import PolicyAction, PolicyContext
from app.guard.sources import RulePolicySource
from app.modules.guard.enforcement import (
    CONTENT_SCAN_PSEUDO_TOOL,
    is_hook_applicable_rule,
    is_tool_result_scan_rule,
)

MARK = "ZZ-CANARY-MARK"


# ── flatteners ───────────────────────────────────────────────────────────────

OPENAI_BODY = {
    "messages": [
        {"role": "user", "content": "user says hello"},
        {"role": "assistant", "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "f", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": f"tool says {MARK}"},
        {"role": "tool", "tool_call_id": "c2", "content": [{"type": "text", "text": "second tool part"}]},
    ],
    "tools": [{"type": "function", "function": {
        "name": "f", "description": "does f",
        "parameters": {"type": "object", "properties": {"x": {"type": "string", "description": "the x value"}}},
    }}],
}


def test_tool_results_openai_chat():
    text = flatten_tool_results(OPENAI_BODY)
    assert f"tool says {MARK}" in text and "second tool part" in text
    assert "user says hello" not in text


def test_tool_results_anthropic_blocks_and_nested_content():
    body = {"messages": [{"role": "user", "content": [
        {"type": "text", "text": "typed by user"},
        {"type": "tool_result", "tool_use_id": "t1", "content": f"anthropic {MARK}"},
        {"type": "tool_result", "tool_use_id": "t2", "content": [{"type": "text", "text": "nested text"}]},
    ]}]}
    text = flatten_tool_results(body)
    assert MARK in text and "nested text" in text and "typed by user" not in text
    # the user flattener must keep ignoring tool_result blocks
    assert flatten_prompt(body) == "typed by user"


def test_tool_results_responses_api_function_call_output():
    body = {"input": [{"type": "function_call_output", "call_id": "c", "output": f"resp {MARK}"}]}
    assert MARK in flatten_tool_results(body)


def test_tool_descriptions_include_parameter_descriptions():
    text = flatten_tool_descriptions(OPENAI_BODY)
    assert "does f" in text and "the x value" in text
    anthropic = {"tools": [{"name": "g", "description": "does g", "input_schema": {"properties": {"y": {"description": "the y"}}}}]}
    assert "does g" in flatten_tool_descriptions(anthropic) and "the y" in flatten_tool_descriptions(anthropic)


def test_flatteners_tolerate_malformed_input():
    assert flatten_tool_results({"messages": [None, "x", {"role": "tool", "content": 5}], "input": [1]}) == ""
    assert flatten_tool_descriptions({"tools": [None, {"function": "bad"}]}) == ""


# ── selector semantics ───────────────────────────────────────────────────────

def _rule(**kw):
    return {"id": "r", "match_pattern": MARK, "action": "block", "gates": ["prompt"], **kw}


def test_rule_without_selector_only_sees_user_text():
    texts = {"user": "clean", "tool_result": MARK, "tool_description": MARK}
    assert not _rule_matches(_rule(), "openai", "m", "clean", source_texts=texts)
    assert _rule_matches(_rule(), "openai", "m", MARK, source_texts={"user": MARK})


@pytest.mark.parametrize("source", ["tool_result", "tool_description"])
def test_selector_opts_in_per_source(source):
    rule = _rule(match_content_source=[source])
    hit: list[str] = []
    assert _rule_matches(rule, "openai", "m", "", source_texts={"user": "", source: MARK}, matched_source=hit)
    assert hit == [source]
    other = "tool_description" if source == "tool_result" else "tool_result"
    assert not _rule_matches(rule, "openai", "m", "", source_texts={"user": "", other: MARK})
    assert not _rule_matches(rule, "openai", "m", MARK, source_texts={"user": MARK})


def test_per_source_pattern_is_narrower_for_tool_content():
    rule = _rule(match_pattern="broad|narrow", match_content_source=["user", "tool_result"],
                 match_pattern_by_source={"tool_result": "narrow"})
    assert _rule_matches(rule, "openai", "m", "", source_texts={"user": "broad", "tool_result": ""})
    assert not _rule_matches(rule, "openai", "m", "", source_texts={"user": "", "tool_result": "broad"})
    assert _rule_matches(rule, "openai", "m", "", source_texts={"user": "", "tool_result": "narrow"})


def test_unknown_sources_are_ignored():
    assert rule_content_sources(_rule(match_content_source=["bogus"])) == []
    assert rule_content_sources(_rule(match_content_source="tool_result")) == ["tool_result"]
    assert rule_content_sources(_rule()) is None
    assert not _rule_matches(_rule(match_content_source=["bogus"]), "openai", "m", MARK)


def test_selector_rule_is_a_proxy_rule():
    assert _is_proxy_rule(_rule(match_content_source=["tool_result"]))


# ── composed engine: decision carries content_source ────────────────────────

@pytest.fixture
def policy_snapshot(monkeypatch):
    rules: list[dict] = []
    monkeypatch.setattr(policy, "SessionLocal", lambda: MagicMock())
    monkeypatch.setattr(policy, "_canonical_workspace_id", lambda workspace: workspace)
    monkeypatch.setattr(policy, "set_workspace_rls", lambda db, workspace: None)
    monkeypatch.setattr(policy, "compute_policy", lambda db, workspace, surface: rules)
    return rules


def _ctx(body):
    return PolicyContext(workspace_id="00000000-0000-0000-0000-000000000001", provider="openai",
                         model="gpt-4o", body=body, gate="prompt")


@pytest.mark.parametrize("body,source", [
    ({"messages": [{"role": "tool", "tool_call_id": "c", "content": MARK}]}, "tool_result"),
    ({"messages": [], "tools": [{"type": "function", "function": {"name": "f", "description": MARK}}]}, "tool_description"),
])
def test_decision_records_content_source(policy_snapshot, body, source):
    policy_snapshot.append(_rule(id="inj", match_content_source=["user", "tool_result", "tool_description"]))
    decision = evaluate_composed(_ctx(body), sources=[RulePolicySource()])
    assert decision.action == PolicyAction.BLOCK
    assert decision.rule_id == "inj"
    assert decision.extras["raw"]["content_source"] == source
    assert decision.matched_rules[0]["content_source"] == source


def test_user_text_still_matches_and_tool_text_is_not_extracted_without_selector(policy_snapshot, monkeypatch):
    called = []
    monkeypatch.setattr(policy, "content_source_texts", lambda *a, **k: called.append(1) or {})
    policy_snapshot.append(_rule(id="legacy"))
    body = {"messages": [{"role": "user", "content": MARK}, {"role": "tool", "content": MARK}]}
    decision = evaluate_composed(_ctx(body), sources=[RulePolicySource()])
    assert decision.action == PolicyAction.BLOCK
    assert decision.extras["raw"]["content_source"] is None
    assert called == []  # nothing opted in, so no extra flattening cost


def test_clean_request_is_allowed(policy_snapshot):
    policy_snapshot.append(_rule(id="inj", match_content_source=["tool_result"]))
    body = {"messages": [{"role": "tool", "tool_call_id": "c", "content": "all good"}]}
    assert evaluate_composed(_ctx(body), sources=[RulePolicySource()]).action == PolicyAction.ALLOW


# ── hook-sync projection ─────────────────────────────────────────────────────

def test_tool_result_scan_rule_detection_and_hook_exclusion():
    rule = _rule(match_content_source=["user", "tool_result"])
    assert is_tool_result_scan_rule(rule)
    assert not is_tool_result_scan_rule(_rule(match_content_source=["tool_description"]))
    assert not is_tool_result_scan_rule(_rule())
    # never treated as a tool-input rule
    assert not is_hook_applicable_rule(rule)
    assert CONTENT_SCAN_PSEUDO_TOOL == "__tool_result__"


# ── per-source action: tool content warns, user text blocks ──────────────────

@pytest.fixture(autouse=True)
def _fresh_seen_cache():
    policy.reset_seen_tool_hits()
    yield
    policy.reset_seen_tool_hits()


def _inj(**kw):
    return _rule(id="inj", match_content_source=["user", "tool_result", "tool_description"],
                 action_by_source={"tool_result": "warn", "tool_description": "warn"}, **kw)


def _run(body):
    return evaluate_composed(_ctx(body), sources=[RulePolicySource()])


def test_user_content_still_blocks(policy_snapshot):
    policy_snapshot.append(_inj())
    decision = _run({"messages": [{"role": "user", "content": MARK}]})
    assert decision.action == PolicyAction.BLOCK
    assert decision.extras["raw"]["content_source"] == "user"


@pytest.mark.parametrize("body,source", [
    ({"messages": [{"role": "tool", "tool_call_id": "c", "content": MARK}]}, "tool_result"),
    ({"messages": [], "tools": [{"type": "function", "function": {"name": "f", "description": MARK}}]}, "tool_description"),
])
def test_tool_content_warns_and_proceeds(policy_snapshot, body, source):
    policy_snapshot.append(_inj(message_by_source={source: "tool content flagged"}))
    decision = _run(body)
    assert decision.action == PolicyAction.WARN
    assert not decision.blocks
    assert decision.extras["raw"]["content_source"] == source
    assert decision.matched_rules[0]["action"] == "warn"
    assert decision.extras["raw"]["message"] == "tool content flagged"


def test_user_block_wins_over_tool_warn_in_same_request(policy_snapshot):
    policy_snapshot.append(_inj())
    body = {"messages": [{"role": "user", "content": MARK}, {"role": "tool", "content": MARK}]}
    assert _run(body).action == PolicyAction.BLOCK


def test_replayed_history_never_blocks_and_warns_once(policy_snapshot):
    policy_snapshot.append(_inj())
    history = [{"role": "tool", "tool_call_id": "c", "content": f"article quoting {MARK} here"}]
    actions = [
        _run({"messages": history + [{"role": "user", "content": f"follow-up {turn}"}]}).action
        for turn in range(4)
    ]
    assert PolicyAction.BLOCK not in actions
    assert actions == [PolicyAction.WARN, PolicyAction.ALLOW, PolicyAction.ALLOW, PolicyAction.ALLOW]


def test_new_tool_content_after_dedupe_still_warns(policy_snapshot):
    policy_snapshot.append(_inj())
    first = {"messages": [{"role": "tool", "content": f"page one {MARK}"}]}
    second = {"messages": [{"role": "tool", "content": f"page one {MARK}"},
                           {"role": "tool", "content": f"an entirely different page, also {MARK}, elsewhere"}]}
    assert _run(first).action == PolicyAction.WARN
    assert _run(second).action == PolicyAction.WARN


def test_blocking_tool_hit_is_never_deduped(policy_snapshot):
    policy_snapshot.append(_rule(id="inj", match_content_source=["tool_result"]))  # plain block, no override
    body = {"messages": [{"role": "tool", "content": MARK}]}
    for _ in range(3):
        assert _run(body).action == PolicyAction.BLOCK


def test_effective_action_helpers():
    rule = _inj(message_by_source={"tool_result": "m"})
    assert policy.effective_action(rule, "user") == "block"
    assert policy.effective_action(rule, "tool_result") == "warn"
    assert policy.effective_action({**rule, "action_by_source": {"tool_result": "bogus"}}, "tool_result") == "block"
    assert policy.effective_message(rule, "tool_result") == "m"


def test_validate_action_by_source():
    from app.modules.guard.enforcement import EnforcementMetadataError, validate_action_by_source
    validate_action_by_source(_inj())
    with pytest.raises(EnforcementMetadataError):
        validate_action_by_source(_rule(action_by_source={"tool_result": "warn"}))
    with pytest.raises(EnforcementMetadataError):
        validate_action_by_source(_rule(match_content_source=["user"], action_by_source={"tool_result": "warn"}))
    with pytest.raises(EnforcementMetadataError):
        validate_action_by_source(_rule(match_content_source=["tool_result"], action_by_source={"tool_result": "nope"}))


def test_hook_projection_ships_tool_result_action(monkeypatch):
    from app.modules.guard import enforcement
    monkeypatch.setattr("app.modules.guard.policy_engine.compute_policy",
                        lambda db, ws, surface: [_inj(message_by_source={"tool_result": "m"})])
    (shipped,) = enforcement.tool_result_scan_rules(MagicMock(), "ws")
    assert shipped["action"] == "warn" and shipped["message"] == "m"


def test_shipped_pack_rule_blocks_user_and_warns_on_tool_content(policy_snapshot):
    import json
    from pathlib import Path
    path = Path(policy.__file__).parents[1] / "modules/guard/skill_packs/conduct-base.json"
    rule = next(r for r in json.loads(path.read_text())["rules"] if r["id"] == "proxy-no-prompt-injection")
    # pattern configured in-test with the synthetic marker, not a real payload
    rule = {**rule, "gates": ["prompt"], "match_pattern": MARK,
            "match_pattern_by_source": {"tool_result": MARK, "tool_description": MARK}}
    policy_snapshot.append(rule)
    assert _run({"messages": [{"role": "user", "content": MARK}]}).action == PolicyAction.BLOCK
    assert _run({"messages": [{"role": "tool", "content": MARK}]}).action == PolicyAction.WARN
