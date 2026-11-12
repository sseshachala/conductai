"""Tier-gated rules must not leak to hook clients as unconditional rules.

Regression: a Cedar `forbid when context.risk_tier == "tier_3"` with an empty
action mapped to match_tool="*" + match_agent_risk_tier="tier_3". /policies/sync
dropped the tier field, so every hook — any tier — blocked every tool.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.modules.guard.cedar_adapter.mapper import cedar_json_to_rule
from app.modules.guard.enforcement import is_hook_applicable_rule
from app.modules.guard.routers import policies_read

SAMPLE = Path(__file__).resolve().parents[3] / "docs/guard/examples/tier3-no-shell.json"

TIER3_ANY_TOOL = {"id": "t3", "match_tool": "*", "match_agent_risk_tier": "tier_3", "action": "block"}
PLAIN = {"id": "plain", "match_pattern": r"rm\s+-rf", "action": "block"}


@pytest.mark.parametrize("caller,shipped", [("tier_3", True), ("tier_1", False), ("tier_2", False), (None, False)])
def test_tier_rule_ships_only_to_matching_caller(caller, shipped):
    assert is_hook_applicable_rule(TIER3_ANY_TOOL, caller_risk_tier=caller) is shipped


def test_untiered_rule_ships_to_everyone():
    for caller in (None, "tier_1", "tier_3"):
        assert is_hook_applicable_rule(PLAIN, caller_risk_tier=caller)


@pytest.mark.parametrize("extra", [
    {"match_model": "gpt-4o"}, {"match_prompt": "secret"}, {"match_provider": "openai"},
    {"match_tokens_before_gt": 1000}, {"match_mcp_server": "github"}, {"match_some_future_field": "x"},
])
def test_conditions_the_hook_cannot_evaluate_stay_server_side(extra):
    # Shipping these would silently drop the condition and widen the rule.
    assert not is_hook_applicable_rule({**PLAIN, **extra})


def test_rule_with_no_hook_condition_is_not_shipped():
    assert not is_hook_applicable_rule({"id": "x", "match_model": "gpt-4o", "action": "block"})


def test_sample_policy_is_shell_only_and_tier_gated():
    rule = cedar_json_to_rule(json.loads(SAMPLE.read_text())["policies"][0])
    assert set(rule["match_tool"].split(",")) == {"bash", "shell"}
    assert rule["match_agent_risk_tier"] == "tier_3"


# ── /guard/policies/sync end to end (stubbed db) ─────────────────────────────

class _Q:
    def filter(self, *_):
        return self

    def first(self):
        return None


class _DB:
    def query(self, *_):
        return _Q()

    def get(self, *_):
        return None


@pytest.fixture
def sync(monkeypatch):
    monkeypatch.setattr(policies_read, "compute_policy", lambda *a, **k: [TIER3_ANY_TOOL, PLAIN])
    monkeypatch.setattr(policies_read, "_audit_exception_transitions", lambda *a, **k: None)

    def call(tier):
        monkeypatch.setattr("app.core.auth.caller_risk_tier", lambda token, db: tier if token else None)
        out = policies_read.sync_policies(
            workspace_id="fd4b6608-f320-44b8-af22-fc579bd53600", db=_DB(), _auth="ws",
            authorization="Bearer cond_agt_test",
        )
        return {r.rule_id for r in out.rules}
    return call


def test_sync_tier1_caller_does_not_get_tier3_rule(sync):
    assert sync("tier_1") == {"plain"}


def test_sync_tier3_caller_gets_tier3_rule(sync):
    assert sync("tier_3") == {"t3", "plain"}


def test_sync_unknown_identity_does_not_get_tier_rules(sync):
    assert sync(None) == {"plain"}


def test_sync_carries_pack_except_paths(monkeypatch):
    # Regression: /policies/sync dropped except_paths, so a pack's path exemptions
    # (e.g. its own test fixtures) were only honoured until the first sync.
    exempt = {**PLAIN, "except_paths": ["tests/fixtures/guard_packs"]}
    monkeypatch.setattr(policies_read, "compute_policy", lambda *a, **k: [exempt])
    monkeypatch.setattr(policies_read, "_audit_exception_transitions", lambda *a, **k: None)
    monkeypatch.setattr("app.core.auth.caller_risk_tier", lambda token, db: None)
    out = policies_read.sync_policies(
        workspace_id="fd4b6608-f320-44b8-af22-fc579bd53600", db=_DB(), _auth="ws",
        authorization="Bearer cond_agt_test",
    )
    assert out.rules[0].except_paths == ["tests/fixtures/guard_packs"]
