"""Tests for resolve_for_workspace() DB wrapper."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.runtime.model_router import resolve_for_workspace
from app.routers.workspace_llm_primitives import DEFAULT_PREFERRED_PROVIDER, DEFAULT_TIER_MAPS


class _Row:
    def __init__(self, preferred_provider, tier_map):
        self.preferred_provider = preferred_provider
        self.tier_map = tier_map


def _db_with(row):
    db = MagicMock()
    db.get.return_value = row
    return db


def test_no_workspace_id_returns_defaults():
    provider, model, _ = resolve_for_workspace(None, "", routing_preference="balanced")
    assert provider == DEFAULT_PREFERRED_PROVIDER
    assert model == DEFAULT_TIER_MAPS[DEFAULT_PREFERRED_PROVIDER]["balanced"]


def test_no_db_returns_defaults():
    provider, model, _ = resolve_for_workspace(None, "some-ws-uuid", routing_preference="smart")
    assert provider == DEFAULT_PREFERRED_PROVIDER
    assert model == DEFAULT_TIER_MAPS[DEFAULT_PREFERRED_PROVIDER]["smart"]


def test_missing_row_returns_defaults():
    db = _db_with(None)
    provider, model, _ = resolve_for_workspace(db, "ws-1", routing_preference="cheap")
    assert provider == DEFAULT_PREFERRED_PROVIDER
    assert model == DEFAULT_TIER_MAPS[DEFAULT_PREFERRED_PROVIDER]["cheap"]


def test_row_with_custom_provider_and_tier_map():
    row = _Row(
        preferred_provider="openai",
        tier_map={"openai": {"cheap": "gpt-4o-mini", "balanced": "gpt-4o", "smart": "gpt-4o"}},
    )
    db = _db_with(row)
    provider, model, reason = resolve_for_workspace(db, "ws-2", routing_preference="balanced")
    assert provider == "openai"
    assert model == "gpt-4o"
    assert "workspace openai" in reason


def test_row_with_empty_tier_map_falls_back_to_defaults():
    row = _Row(preferred_provider="anthropic", tier_map={})
    db = _db_with(row)
    provider, model, _ = resolve_for_workspace(db, "ws-3", routing_preference="smart")
    assert provider == "anthropic"
    assert model == DEFAULT_TIER_MAPS["anthropic"]["smart"]


def test_row_forces_explicit_provider_via_tier_map():
    row = _Row(
        preferred_provider="anthropic",
        tier_map={"anthropic": {"balanced": "claude-sonnet-4-6"}, "openai": {"balanced": "gpt-4.1"}},
    )
    db = _db_with(row)
    provider, model, _ = resolve_for_workspace(db, "ws-4", routing_preference="balanced", explicit_provider="openai")
    assert provider == "openai"
    assert model == "gpt-4.1"


def test_explicit_model_bypasses_workspace_lookup():
    row = _Row(preferred_provider="anthropic", tier_map={"anthropic": {"balanced": "claude-sonnet-4-6"}})
    db = _db_with(row)
    provider, model, reason = resolve_for_workspace(db, "ws-5", routing_preference="balanced", explicit_model="gpt-4.1")
    assert provider == "openai"
    assert model == "gpt-4.1"
    assert reason == "user-pinned model"
