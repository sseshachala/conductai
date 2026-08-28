"""Guard proxy tier-form model string resolution (PR B.5 of #1347).

Verifies _resolve_tier_form() pass-through vs resolve behaviour; DB path
is exercised via a monkeypatched resolve_for_workspace to keep the test
free of a Postgres dependency.
"""
from __future__ import annotations

import pytest

from app.modules.guard.routers.proxy import _resolve_tier_form


@pytest.fixture
def stub_router(monkeypatch):
    calls = []

    def _fake(db, workspace_id, routing_preference, explicit_model=None, explicit_provider=None):
        calls.append({
            "workspace_id": workspace_id,
            "routing_preference": routing_preference,
            "explicit_provider": explicit_provider,
        })
        # emulate primitives table: cheap/balanced/smart per provider
        table = {
            "anthropic": {"cheap": "claude-haiku-4-5-20251001", "balanced": "claude-sonnet-4-6", "smart": "claude-opus-4-7"},
            "openai":    {"cheap": "gpt-4.1-mini", "balanced": "gpt-4.1", "smart": "gpt-4.1"},
        }
        return explicit_provider, table[explicit_provider][routing_preference], "stubbed"

    monkeypatch.setattr("app.runtime.model_router.resolve_for_workspace", _fake)
    return calls


def test_concrete_model_id_passes_through(stub_router):
    assert _resolve_tier_form(db=None, workspace_id="ws", endpoint_provider="openai", model_field="gpt-4.1") is None
    assert stub_router == []


def test_bare_tier_resolves_via_endpoint_provider(stub_router):
    out = _resolve_tier_form(db=None, workspace_id="ws", endpoint_provider="openai", model_field="balanced")
    assert out == "gpt-4.1"
    assert stub_router[0]["explicit_provider"] == "openai"
    assert stub_router[0]["routing_preference"] == "balanced"


def test_provider_prefixed_tier_matches_endpoint(stub_router):
    out = _resolve_tier_form(db=None, workspace_id="ws", endpoint_provider="anthropic", model_field="anthropic/smart")
    assert out == "claude-opus-4-7"
    assert stub_router[-1]["explicit_provider"] == "anthropic"
    assert stub_router[-1]["routing_preference"] == "smart"


def test_cross_provider_prefix_is_ignored(stub_router):
    # Caller hit /openai/... but sent anthropic/balanced — endpoint provider wins,
    # helper returns None so the raw string flows to upstream unchanged.
    assert _resolve_tier_form(db=None, workspace_id="ws", endpoint_provider="openai", model_field="anthropic/balanced") is None
    assert stub_router == []


def test_bogus_tail_after_valid_provider_prefix_is_ignored(stub_router):
    assert _resolve_tier_form(db=None, workspace_id="ws", endpoint_provider="openai", model_field="openai/foo") is None
    assert stub_router == []


def test_empty_or_non_string_input(stub_router):
    assert _resolve_tier_form(db=None, workspace_id="ws", endpoint_provider="openai", model_field="") is None
    assert _resolve_tier_form(db=None, workspace_id="ws", endpoint_provider="openai", model_field=None) is None
    assert _resolve_tier_form(db=None, workspace_id="ws", endpoint_provider="openai", model_field=42) is None
    assert stub_router == []


# ── _apply_tier_resolution — mirrors the _proxy() insertion point ──────────

from app.modules.guard.routers.proxy import _apply_tier_resolution


def test_apply_concrete_model_leaves_body_unchanged(stub_router):
    body = {"model": "gpt-4.1", "messages": []}
    model, tier_form = _apply_tier_resolution(db=None, workspace_id="ws", endpoint_provider="openai", body=body)
    assert model == "gpt-4.1"
    assert tier_form is None
    assert body["model"] == "gpt-4.1"
    assert stub_router == []


def test_apply_bare_tier_rewrites_body_and_returns_tier_form(stub_router):
    body = {"model": "balanced", "messages": []}
    model, tier_form = _apply_tier_resolution(db=None, workspace_id="ws", endpoint_provider="openai", body=body)
    assert model == "gpt-4.1"
    assert tier_form == "balanced"
    assert body["model"] == "gpt-4.1"
    # order matters: helper must call resolver before mutating body
    assert stub_router[0]["explicit_provider"] == "openai"


def test_apply_provider_prefixed_tier(stub_router):
    body = {"model": "anthropic/smart", "messages": []}
    model, tier_form = _apply_tier_resolution(db=None, workspace_id="ws", endpoint_provider="anthropic", body=body)
    assert model == "claude-opus-4-7"
    assert tier_form == "anthropic/smart"
    assert body["model"] == "claude-opus-4-7"


def test_apply_cross_provider_prefix_is_ignored(stub_router):
    body = {"model": "anthropic/balanced", "messages": []}
    model, tier_form = _apply_tier_resolution(db=None, workspace_id="ws", endpoint_provider="openai", body=body)
    # endpoint provider is authoritative; cross-provider prefix returns None
    assert model == "anthropic/balanced"
    assert tier_form is None
    assert body["model"] == "anthropic/balanced"
    assert stub_router == []


def test_apply_missing_model_field_returns_unknown(stub_router):
    body = {"messages": []}
    model, tier_form = _apply_tier_resolution(db=None, workspace_id="ws", endpoint_provider="openai", body=body)
    assert model == "unknown"
    assert tier_form is None
    assert "model" not in body
