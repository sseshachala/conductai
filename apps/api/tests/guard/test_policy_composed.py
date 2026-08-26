"""Unit tests for app.guard.policy.evaluate_composed — #1225 Phase 3."""
from __future__ import annotations

from app.guard.policy import evaluate_composed
from app.guard.policy_types import PolicyAction, PolicyContext, PolicyDecision


def _ctx():
    return PolicyContext(
        workspace_id="ws-1",
        provider="openai",
        model="gpt-4o-mini",
        body={"messages": []},
        clerk_user_id="u-1",
    )


class _StaticSource:
    """Test-only source that returns a fixed decision + records calls."""
    def __init__(self, name: str, decision: PolicyDecision):
        self._name = name
        self._decision = decision
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    def evaluate(self, ctx):
        self.call_count += 1
        return self._decision


def _allow(name="s"):
    return _StaticSource(name, PolicyDecision(action=PolicyAction.ALLOW, source=name))


def _warn(name="s", rule_id=None, guidance=None):
    return _StaticSource(name, PolicyDecision(
        action=PolicyAction.WARN,
        source=name,
        rule_id=rule_id,
        reason="warn",
        inject_guidance=bool(guidance),
        guidance=guidance,
    ))


def _blocker(name="s", rule_id="r-b", reason="denied"):
    return _StaticSource(name, PolicyDecision(
        action=PolicyAction.BLOCK,
        source=name,
        rule_id=rule_id,
        reason=reason,
    ))


# ─── All-allow paths ─────────────────────────────────────────────────────────

def test_no_sources_returns_allow():
    d = evaluate_composed(_ctx(), sources=[])
    assert d.action == PolicyAction.ALLOW
    assert d.source == "empty"


def test_all_allow_returns_allow():
    sources = [_allow("a1"), _allow("a2")]
    d = evaluate_composed(_ctx(), sources=sources)
    assert d.action == PolicyAction.ALLOW


def test_all_sources_called_when_no_block():
    sources = [_allow("a1"), _allow("a2"), _allow("a3")]
    evaluate_composed(_ctx(), sources=sources)
    for s in sources:
        assert s.call_count == 1


# ─── Short-circuit on BLOCK ──────────────────────────────────────────────────

def test_first_block_short_circuits():
    sources = [_allow("a1"), _blocker("bad"), _allow("a3")]
    d = evaluate_composed(_ctx(), sources=sources)
    assert d.action == PolicyAction.BLOCK
    assert d.source == "bad"
    assert sources[0].call_count == 1     # ran
    assert sources[1].call_count == 1     # ran and blocked
    assert sources[2].call_count == 0     # never reached


def test_block_at_position_zero_short_circuits():
    sources = [_blocker("bad"), _allow("a1"), _allow("a2")]
    d = evaluate_composed(_ctx(), sources=sources)
    assert d.action == PolicyAction.BLOCK
    assert sources[1].call_count == 0
    assert sources[2].call_count == 0


def _approval(name="s", rule_id="r-a", reason="human review"):
    return _StaticSource(name, PolicyDecision(
        action=PolicyAction.APPROVAL,
        source=name,
        rule_id=rule_id,
        reason=reason,
    ))


def test_approval_short_circuits():
    """APPROVAL is a terminal state — downstream sources shouldn't run."""
    sources = [_approval("rule"), _allow("cost"), _allow("throughput")]
    d = evaluate_composed(_ctx(), sources=sources)
    assert d.action == PolicyAction.APPROVAL
    assert sources[1].call_count == 0
    assert sources[2].call_count == 0


def test_block_preserves_rule_id_and_reason():
    sources = [_blocker("cap", rule_id="guard.spend_cap", reason="over cap")]
    d = evaluate_composed(_ctx(), sources=sources)
    assert d.rule_id == "guard.spend_cap"
    assert d.reason == "over cap"


# ─── Merge non-blocking decisions ────────────────────────────────────────────

def test_multiple_warns_merged():
    sources = [_warn("s1", rule_id="r1"), _warn("s2", rule_id="r2")]
    d = evaluate_composed(_ctx(), sources=sources)
    assert d.action == PolicyAction.WARN


def test_warn_wins_over_allow_when_no_block():
    sources = [_allow("a"), _warn("w", rule_id="r-w")]
    d = evaluate_composed(_ctx(), sources=sources)
    assert d.action == PolicyAction.WARN
    assert d.rule_id == "r-w"


def test_guidance_from_first_warn_wins():
    sources = [
        _allow("a"),
        _warn("w1", guidance="first"),
        _warn("w2", guidance="second"),
    ]
    d = evaluate_composed(_ctx(), sources=sources)
    assert d.inject_guidance is True
    assert d.guidance == "first"


# ─── Default sources wiring ──────────────────────────────────────────────────

def test_default_sources_used_when_none_passed(monkeypatch):
    # Stub the real rule source's underlying evaluator so no DB call is made.
    from app.guard import sources as _sources

    def _stub(ws, provider, model, body):
        return {"action": "ALLOW", "rule_id": None, "matched_rules": [], "defense_score": 0}

    monkeypatch.setattr(
        _sources.DEFAULT_SOURCES[0], "_evaluator", _stub, raising=False,
    )

    ctx = PolicyContext(
        workspace_id="00000000-0000-0000-0000-000000000000",
        provider="openai",
        model="gpt-4o-mini",
        body={"messages": []},
        db=None,  # cost/throughput sources fail-open when db is None
    )
    d = evaluate_composed(ctx)
    assert d.action == PolicyAction.ALLOW
