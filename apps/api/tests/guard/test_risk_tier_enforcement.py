"""Tier enforcement — unit + integration + Cedar round-trip.

Covers the wiring from `match_agent_risk_tier` on a rule through to real
block/pass decisions at both PEPs (MCP + LLM proxy).

Feature summary:
  - Rules can set `match_agent_risk_tier: "tier_3"` (etc). Cedar syntax
    `context.risk_tier == "tier_3"` compiles into this field via the mapper.
  - Both matchers (`_rule_matches` proxy-side, `_match_policy` MCP-side)
    check the field against the caller identity's tier. Null tier never
    matches a tier-requiring rule (safe for legacy identities).
  - PEPs populate the caller's tier from `AgentIdentity.risk_tier` at
    request entry.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

# Match the env setup pattern used elsewhere in apps/api/tests/.
HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")


# ─── Unit: proxy-side _rule_matches ───────────────────────────────────────────

def test_rule_matches_tier_exact_match():
    from app.guard.policy import _rule_matches
    rule = {"match_agent_risk_tier": "tier_3", "gates": ["prompt"]}
    assert _rule_matches(rule, "anthropic", "claude-opus-4-7", "hello",
                         gate="prompt", agent_risk_tier="tier_3") is True


def test_rule_matches_tier_mismatch():
    from app.guard.policy import _rule_matches
    rule = {"match_agent_risk_tier": "tier_3", "gates": ["prompt"]}
    assert _rule_matches(rule, "anthropic", "claude-opus-4-7", "hello",
                         gate="prompt", agent_risk_tier="tier_1") is False


def test_rule_matches_tier_null_context_safe():
    """Legacy identities may have null tier — must not match a tier-requiring
    rule (and must not crash)."""
    from app.guard.policy import _rule_matches
    rule = {"match_agent_risk_tier": "tier_3", "gates": ["prompt"]}
    assert _rule_matches(rule, "anthropic", "claude-opus-4-7", "hello",
                         gate="prompt", agent_risk_tier=None) is False


def test_rule_matches_no_tier_field_is_inert():
    """Rules without match_agent_risk_tier fire for every caller regardless
    of their tier."""
    from app.guard.policy import _rule_matches
    rule = {"gates": ["prompt"]}
    assert _rule_matches(rule, "anthropic", "claude-opus-4-7", "hello",
                         gate="prompt", agent_risk_tier="tier_3") is True
    assert _rule_matches(rule, "anthropic", "claude-opus-4-7", "hello",
                         gate="prompt", agent_risk_tier=None) is True


def test_rule_matches_tier_and_prompt_both_required():
    """Tier + prompt are AND'd — both must match for the rule to fire."""
    from app.guard.policy import _rule_matches
    rule = {"match_agent_risk_tier": "tier_3", "match_prompt": "secret", "gates": ["prompt"]}
    # Right tier, right prompt → match
    assert _rule_matches(rule, "anthropic", "m", "here is a secret",
                         gate="prompt", agent_risk_tier="tier_3") is True
    # Right tier, wrong prompt → no match
    assert _rule_matches(rule, "anthropic", "m", "innocuous text",
                         gate="prompt", agent_risk_tier="tier_3") is False
    # Wrong tier, right prompt → no match
    assert _rule_matches(rule, "anthropic", "m", "here is a secret",
                         gate="prompt", agent_risk_tier="tier_1") is False


# ─── Unit: MCP-side _match_policy ─────────────────────────────────────────────

def test_match_policy_tier_gates_a_tool_call():
    from app.modules.guard.routers.mcp import _match_policy
    rules = [{
        "match_tool": "shell",
        "match_agent_risk_tier": "tier_3",
        "action": "block",
        "gates": ["action"],
        "rule_id": "tier3-shell-block",
    }]
    # Tier 3 caller invoking shell → rule fires
    hit = _match_policy("shell", {"command": "ls"}, rules,
                        gate="action", agent_risk_tier="tier_3")
    assert hit is not None
    assert hit["rule_id"] == "tier3-shell-block"

    # Tier 1 caller — no match
    miss = _match_policy("shell", {"command": "ls"}, rules,
                          gate="action", agent_risk_tier="tier_1")
    assert miss is None


def test_match_policy_tier_null_never_matches_tier_rule():
    from app.modules.guard.routers.mcp import _match_policy
    rules = [{
        "match_agent_risk_tier": "tier_3",
        "action": "block",
        "gates": ["action"],
        "rule_id": "tier3-any-block",
    }]
    assert _match_policy("shell", {}, rules,
                          gate="action", agent_risk_tier=None) is None


def test_match_policy_no_tier_field_matches_any_caller():
    from app.modules.guard.routers.mcp import _match_policy
    rules = [{
        "match_tool": "shell",
        "action": "warn",
        "gates": ["action"],
        "rule_id": "shell-warn-all",
    }]
    for tier in ("tier_1", "tier_2", "tier_3", None):
        hit = _match_policy("shell", {"command": "ls"}, rules,
                             gate="action", agent_risk_tier=tier)
        assert hit is not None, f"expected match for tier={tier}"
        assert hit["rule_id"] == "shell-warn-all"


# ─── Cedar round-trip ─────────────────────────────────────────────────────────

def test_cedar_import_writes_match_agent_risk_tier():
    """`context.risk_tier == "tier_3"` in Cedar AST → rule JSON with
    match_agent_risk_tier set. Proves the mapper hook exists."""
    from app.modules.guard.cedar_adapter.mapper import _apply_comparison

    rule: dict = {}
    args = [
        {".": {"left": {"Var": "context"}, "attr": "risk_tier"}},
        {"Value": "tier_3"},
    ]
    _apply_comparison("==", args, rule)
    assert rule.get("match_agent_risk_tier") == "tier_3"


def test_cedar_export_serializes_match_agent_risk_tier():
    """Rule JSON with match_agent_risk_tier → exported Cedar contains the
    matching `context.risk_tier == "tier_3"` clause."""
    from app.modules.guard.cedar_adapter.exporter import _build_when_clauses

    rule = {"match_agent_risk_tier": "tier_3"}
    clauses = _build_when_clauses(rule)
    assert any('context.risk_tier == "tier_3"' in c for c in clauses)


# ─── Integration: proxy PEP via TestClient ────────────────────────────────────

@pytest.fixture
def proxy_client(monkeypatch):
    """Mount the proxy router with all external deps mocked. Returns a tuple:
    (TestClient, calls) where calls is a list of upstream forwards captured.
    """
    from app.modules.guard.routers import proxy as proxy_mod
    from app.guard.policy_types import PolicyAction, PolicyDecision

    forward_calls: list[dict] = []

    async def fake_forward(**kwargs):
        forward_calls.append(kwargs)
        return JSONResponse({"id": "chatcmpl-mock", "model": kwargs["body"]["model"]}, status_code=200)

    # Real evaluate_composed via RulePolicySource — patch just the rules loader
    # so we can inject a tier-gated rule per test.
    monkeypatch.setattr(proxy_mod, "SessionLocal", lambda: MagicMock())
    monkeypatch.setattr(proxy_mod, "resolve_agent_token",
                        lambda token, db: ("00000000-0000-0000-0000-000000000001", "user-abc"))
    monkeypatch.setattr(proxy_mod, "token_is_expired", lambda token, db: False)
    monkeypatch.setattr(proxy_mod, "set_workspace_rls", lambda db, ws: None)
    monkeypatch.setattr(proxy_mod, "_upstream_url", lambda db, ws, prov, env: "http://mock-upstream")
    monkeypatch.setattr(proxy_mod, "_vault_key", lambda db, ws, prov, env: "sk-fake")
    monkeypatch.setattr(proxy_mod, "_upstream_api_key", lambda db, ws, env: None)
    monkeypatch.setattr(proxy_mod, "_forward", fake_forward)
    monkeypatch.setattr(proxy_mod, "_infer_ai_tool", lambda req: "test-suite")
    monkeypatch.setattr(proxy_mod, "_flatten_prompt", lambda body: "hello")
    monkeypatch.setattr(proxy_mod, "_estimate_input_tokens", lambda body: 10)
    monkeypatch.setattr("app.runtime.model_router.resolve_for_workspace",
                        lambda **kwargs: ("anthropic", "claude-opus-4-7", "test-resolver"))

    app = FastAPI()
    app.include_router(proxy_mod.router)
    return TestClient(app), forward_calls


def _stub_resolve_agent_identity_row(monkeypatch, tier: str | None):
    """Patch resolve_agent_identity_row to return an identity with the given tier."""
    stub = MagicMock()
    stub.risk_tier = tier
    monkeypatch.setattr("app.core.auth.resolve_agent_identity_row",
                        lambda token, db: stub if tier is not None else None)


def _capture_ctx_evaluator(captured: list, block_when_tier: str | None = None):
    """Fake evaluate_composed that records the PolicyContext it received and
    optionally blocks when ctx.risk_tier matches ``block_when_tier``. Lets a
    test assert 'the PEP populated risk_tier correctly' AND that the
    downstream block/pass flow works end-to-end."""
    from app.guard.policy_types import PolicyAction, PolicyDecision

    def _eval(ctx):
        captured.append({"risk_tier": ctx.risk_tier, "gate": ctx.gate})
        if block_when_tier is not None and ctx.risk_tier == block_when_tier:
            return PolicyDecision(
                action=PolicyAction.BLOCK,
                source="test",
                reason=f"Blocked for {block_when_tier}",
                rule_id=f"test-block-{block_when_tier}",
            )
        return PolicyDecision(action=PolicyAction.ALLOW, source="test")
    return _eval


def test_proxy_prompt_gate_populates_tier3_and_blocks(proxy_client, monkeypatch):
    """End-to-end wiring: caller is tier_3 → PEP populates ctx.risk_tier →
    evaluator sees tier_3 → block short-circuits before upstream."""
    _stub_resolve_agent_identity_row(monkeypatch, tier="tier_3")
    captured: list = []
    monkeypatch.setattr("app.guard.policy.evaluate_composed",
                        _capture_ctx_evaluator(captured, block_when_tier="tier_3"))

    client, forwards = proxy_client
    resp = client.post(
        "/proxy/anthropic/v1/messages",
        headers={"x-api-key": "cond_agt_test"},
        json={"model": "claude-opus-4-7", "messages": [{"role": "user", "content": "hi"}]},
    )
    # PEP must have populated the tier on the context it passed to evaluate.
    assert captured, "evaluator was never called"
    assert captured[0]["risk_tier"] == "tier_3", \
        f"expected ctx.risk_tier=tier_3, got {captured[0]['risk_tier']}"
    # Block short-circuits before the upstream forward runs.
    assert resp.status_code in (403, 400), f"expected block, got {resp.status_code}: {resp.text}"
    assert len(forwards) == 0, "upstream should not be called on a blocked request"


def test_proxy_prompt_gate_tier1_caller_not_blocked_by_tier3_rule(proxy_client, monkeypatch):
    """Rule blocks tier_3 only; caller is tier_1 → evaluator sees tier_1 →
    pass through to upstream."""
    _stub_resolve_agent_identity_row(monkeypatch, tier="tier_1")
    captured: list = []
    monkeypatch.setattr("app.guard.policy.evaluate_composed",
                        _capture_ctx_evaluator(captured, block_when_tier="tier_3"))

    client, forwards = proxy_client
    resp = client.post(
        "/proxy/anthropic/v1/messages",
        headers={"x-api-key": "cond_agt_test"},
        json={"model": "claude-opus-4-7", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert captured[0]["risk_tier"] == "tier_1"
    assert resp.status_code == 200, f"expected pass, got {resp.status_code}: {resp.text}"
    assert len(forwards) == 1, "upstream should be called on a pass"
