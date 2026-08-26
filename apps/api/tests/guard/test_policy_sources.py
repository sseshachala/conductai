"""Unit tests for app.guard.sources — three PolicySource wrappers via DI."""
from __future__ import annotations

from types import SimpleNamespace

from app.guard.policy_types import PolicyAction, PolicyContext
from app.guard.sources import (
    DEFAULT_SOURCES,
    RulePolicySource,
    SpendCapPolicySource,
    ThroughputCapPolicySource,
)


def _ctx(**over):
    base = dict(
        workspace_id="ws-1",
        provider="openai",
        model="gpt-4o-mini",
        body={"messages": [{"role": "user", "content": "hi"}]},
        clerk_user_id="user_test",
        agent_identity_id=None,
        input_tokens=10,
        db=object(),
    )
    base.update(over)
    return PolicyContext(**base)


# ─── RulePolicySource ────────────────────────────────────────────────────────

def test_rule_source_allow():
    fake_evaluator = lambda ws, prov, model, body: {
        "action": "ALLOW", "rule_id": None, "matched_rules": [], "defense_score": 0,
    }
    d = RulePolicySource(evaluator=fake_evaluator).evaluate(_ctx())
    assert d.action == PolicyAction.ALLOW
    assert d.source == "rule"


def test_rule_source_block():
    fake_evaluator = lambda ws, prov, model, body: {
        "action": "BLOCK", "rule_id": "r-42", "message": "no secrets",
        "matched_rules": [{"rule_id": "r-42"}], "defense_score": 5,
    }
    d = RulePolicySource(evaluator=fake_evaluator).evaluate(_ctx())
    assert d.action == PolicyAction.BLOCK
    assert d.rule_id == "r-42"
    assert d.defense_score == 5


def test_rule_source_warn_with_guidance():
    fake_evaluator = lambda ws, prov, model, body: {
        "action": "WARN", "rule_id": "r-1",
        "message": "be careful",
        "matched_rules": [{"rule_id": "r-1"}], "defense_score": 2,
        "inject_guidance": True, "guidance": "Do not paste secrets.",
    }
    d = RulePolicySource(evaluator=fake_evaluator).evaluate(_ctx())
    assert d.action == PolicyAction.WARN
    assert d.inject_guidance is True
    assert d.guidance == "Do not paste secrets."


def test_rule_source_unknown_action_falls_back_to_allow():
    fake_evaluator = lambda ws, prov, model, body: {"action": "MAYBE"}
    d = RulePolicySource(evaluator=fake_evaluator).evaluate(_ctx())
    assert d.action == PolicyAction.ALLOW


def test_rule_source_name():
    assert RulePolicySource().name == "rule"


# ─── SpendCapPolicySource ────────────────────────────────────────────────────

def _spend_result(**kw):
    kw.setdefault("monthly_cost_usd", 0.0)
    kw.setdefault("hard_limit_usd", None)
    kw.setdefault("reason", None)
    return SimpleNamespace(**kw)


def test_spend_cap_no_db_returns_allow():
    d = SpendCapPolicySource().evaluate(_ctx(db=None))
    assert d.action == PolicyAction.ALLOW
    assert d.source == "spend_cap"


def test_spend_cap_under_limit():
    fake_checker = lambda **kw: _spend_result(
        hard_blocked=False, monthly_cost_usd=12.5, hard_limit_usd=100.0,
    )
    d = SpendCapPolicySource(checker=fake_checker).evaluate(_ctx())
    assert d.action == PolicyAction.ALLOW
    assert d.extras["monthly_cost_usd"] == 12.5


def test_spend_cap_over_limit_blocks():
    fake_checker = lambda **kw: _spend_result(
        hard_blocked=True, reason="cap reached",
        monthly_cost_usd=105.0, hard_limit_usd=100.0,
    )
    d = SpendCapPolicySource(checker=fake_checker).evaluate(_ctx())
    assert d.action == PolicyAction.BLOCK
    assert d.reason == "cap reached"
    assert d.rule_id == "guard.spend_cap"


def test_spend_cap_exception_returns_allow():
    def boom(**kw): raise RuntimeError("db down")
    d = SpendCapPolicySource(checker=boom).evaluate(_ctx())
    assert d.action == PolicyAction.ALLOW
    assert "unavailable" in (d.reason or "")


def test_spend_cap_name():
    assert SpendCapPolicySource().name == "spend_cap"


# ─── ThroughputCapPolicySource ───────────────────────────────────────────────

def _throughput_result(**kw):
    kw.setdefault("reason", None)
    kw.setdefault("metric", None)
    kw.setdefault("limit", None)
    kw.setdefault("current", None)
    kw.setdefault("scope", "none")
    return SimpleNamespace(**kw)


def test_throughput_cap_no_db_returns_allow():
    d = ThroughputCapPolicySource().evaluate(_ctx(db=None))
    assert d.action == PolicyAction.ALLOW
    assert d.source == "throughput_cap"


def test_throughput_cap_within():
    fake_checker = lambda db, **kw: _throughput_result(limited=False)
    d = ThroughputCapPolicySource(checker=fake_checker).evaluate(_ctx())
    assert d.action == PolicyAction.ALLOW


def test_throughput_cap_exceeded_blocks():
    fake_checker = lambda db, **kw: _throughput_result(
        limited=True, reason="RPM hit",
        metric="rpm", limit=60, current=61, scope="agent",
    )
    d = ThroughputCapPolicySource(checker=fake_checker).evaluate(_ctx())
    assert d.action == PolicyAction.BLOCK
    assert d.extras["metric"] == "rpm"
    assert d.rule_id == "guard.throughput_cap"


def test_throughput_cap_exception_returns_allow():
    def boom(db, **kw): raise RuntimeError("redis down")
    d = ThroughputCapPolicySource(checker=boom).evaluate(_ctx())
    assert d.action == PolicyAction.ALLOW


def test_throughput_cap_name():
    assert ThroughputCapPolicySource().name == "throughput_cap"


# ─── DEFAULT_SOURCES ordering ────────────────────────────────────────────────

def test_default_sources_ordering():
    names = [s.name for s in DEFAULT_SOURCES]
    assert names == ["rule", "spend_cap", "throughput_cap"]


def test_default_sources_all_have_protocol_shape():
    for s in DEFAULT_SOURCES:
        assert hasattr(s, "name")
        assert callable(s.evaluate)
