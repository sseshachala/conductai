"""Unit tests for app.guard.policy_types — merge + rank + protocol compliance."""
from __future__ import annotations

from app.guard.policy_types import (
    PolicyAction,
    PolicyContext,
    PolicyDecision,
    PolicySource,
    merge_decisions,
)


def _ctx(**over) -> PolicyContext:
    base = dict(workspace_id="ws-1", provider="openai", model="gpt-4o-mini", body={"messages": []})
    base.update(over)
    return PolicyContext(**base)


# ─── Basic construction ──────────────────────────────────────────────────────

def test_action_enum_values():
    assert PolicyAction.ALLOW.value == "ALLOW"
    assert PolicyAction.BLOCK.value == "BLOCK"


def test_decision_blocks_property():
    d = PolicyDecision(action=PolicyAction.BLOCK, source="rule")
    assert d.blocks is True
    assert d.needs_approval is False


def test_decision_needs_approval_property():
    d = PolicyDecision(action=PolicyAction.APPROVAL, source="rule")
    assert d.blocks is False
    assert d.needs_approval is True


def test_context_defaults():
    c = _ctx()
    assert c.clerk_user_id is None
    assert c.input_tokens == 0
    assert c.db is None
    assert c.extras == {}


# ─── merge_decisions — empty + single ────────────────────────────────────────

def test_merge_empty_returns_allow():
    result = merge_decisions([])
    assert result.action == PolicyAction.ALLOW
    assert result.source == "empty"


def test_merge_single_returns_same():
    d = PolicyDecision(action=PolicyAction.WARN, source="rule", rule_id="r1")
    result = merge_decisions([d])
    assert result is d


# ─── merge_decisions — winner selection ──────────────────────────────────────

def test_merge_block_wins_over_warn():
    result = merge_decisions([
        PolicyDecision(action=PolicyAction.WARN, source="rule"),
        PolicyDecision(action=PolicyAction.BLOCK, source="limit"),
    ])
    assert result.action == PolicyAction.BLOCK


def test_merge_approval_wins_over_warn():
    result = merge_decisions([
        PolicyDecision(action=PolicyAction.WARN, source="rule"),
        PolicyDecision(action=PolicyAction.APPROVAL, source="rule"),
    ])
    assert result.action == PolicyAction.APPROVAL


def test_merge_warn_wins_over_allow():
    result = merge_decisions([
        PolicyDecision(action=PolicyAction.ALLOW, source="rule"),
        PolicyDecision(action=PolicyAction.WARN, source="cost"),
    ])
    assert result.action == PolicyAction.WARN


def test_merge_all_allow_stays_allow():
    result = merge_decisions([
        PolicyDecision(action=PolicyAction.ALLOW, source="rule"),
        PolicyDecision(action=PolicyAction.ALLOW, source="cost"),
    ])
    assert result.action == PolicyAction.ALLOW


# ─── merge_decisions — accumulation ──────────────────────────────────────────

def test_merge_matched_rules_accumulate():
    result = merge_decisions([
        PolicyDecision(action=PolicyAction.WARN, source="rule", matched_rules=[{"id": "r1"}]),
        PolicyDecision(action=PolicyAction.WARN, source="rule2", matched_rules=[{"id": "r2"}, {"id": "r3"}]),
    ])
    assert len(result.matched_rules) == 3
    ids = {r["id"] for r in result.matched_rules}
    assert ids == {"r1", "r2", "r3"}


def test_merge_defense_score_sums():
    result = merge_decisions([
        PolicyDecision(action=PolicyAction.WARN, source="rule", defense_score=5),
        PolicyDecision(action=PolicyAction.WARN, source="rule2", defense_score=3),
    ])
    assert result.defense_score == 8


def test_merge_extras_namespaced_by_source():
    result = merge_decisions([
        PolicyDecision(action=PolicyAction.WARN, source="cost", extras={"cost_usd": 4.20}),
        PolicyDecision(action=PolicyAction.WARN, source="throttle", extras={"metric": "rpm"}),
    ])
    assert result.extras == {
        "cost": {"cost_usd": 4.20},
        "throttle": {"metric": "rpm"},
    }


def test_merge_inject_guidance_first_wins():
    result = merge_decisions([
        PolicyDecision(action=PolicyAction.WARN, source="rule",
                       inject_guidance=True, guidance="be careful"),
        PolicyDecision(action=PolicyAction.WARN, source="rule2",
                       inject_guidance=True, guidance="alternate advice"),
    ])
    assert result.inject_guidance is True
    assert result.guidance == "be careful"


def test_merge_inject_guidance_off_when_none_set():
    result = merge_decisions([
        PolicyDecision(action=PolicyAction.WARN, source="rule"),
        PolicyDecision(action=PolicyAction.WARN, source="rule2"),
    ])
    assert result.inject_guidance is False
    assert result.guidance is None


def test_merge_winner_rule_id_and_reason_preserved():
    result = merge_decisions([
        PolicyDecision(action=PolicyAction.WARN, source="rule", rule_id="r1", reason="mild"),
        PolicyDecision(action=PolicyAction.BLOCK, source="limit", rule_id="r2", reason="over-cap"),
    ])
    assert result.rule_id == "r2"
    assert result.reason == "over-cap"


def test_merge_source_field_joins_non_allow_sources():
    result = merge_decisions([
        PolicyDecision(action=PolicyAction.ALLOW, source="allower"),
        PolicyDecision(action=PolicyAction.WARN, source="rule"),
        PolicyDecision(action=PolicyAction.WARN, source="cost"),
    ])
    assert result.source == "cost,rule"


# ─── PolicySource protocol compliance ────────────────────────────────────────

class _MockAlwaysAllow:
    @property
    def name(self) -> str:
        return "mock-allow"

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        return PolicyDecision(action=PolicyAction.ALLOW, source=self.name)


class _MockAlwaysBlock:
    @property
    def name(self) -> str:
        return "mock-block"

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision:
        return PolicyDecision(action=PolicyAction.BLOCK, source=self.name, reason="test-block")


def test_source_protocol_structural_compliance():
    allow_src: PolicySource = _MockAlwaysAllow()
    block_src: PolicySource = _MockAlwaysBlock()
    ctx = _ctx()
    assert allow_src.evaluate(ctx).action == PolicyAction.ALLOW
    assert block_src.evaluate(ctx).action == PolicyAction.BLOCK
    assert allow_src.name == "mock-allow"
    assert block_src.name == "mock-block"
