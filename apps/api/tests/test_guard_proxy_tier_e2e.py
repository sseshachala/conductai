"""E2E TestClient integration for the Guard proxy tier-form path.

Verifies POST /proxy/openai/v1/chat/completions with model="balanced"
rewrites body["model"] to a concrete ID before the upstream forward.

Auth, DB, policy, vault, and upstream HTTP are all patched — we\'re
proving the flow inside _proxy(), not those dependencies.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.guard.policy_types import PolicyAction, PolicyDecision


@pytest.fixture
def client_and_capture(monkeypatch):
    """Mount the proxy router with all external deps mocked; return a
    (TestClient, captured_forward_calls) tuple."""
    from app.modules.guard.routers import proxy as proxy_mod

    forward_calls: list[dict] = []

    async def fake_forward(**kwargs):
        forward_calls.append(kwargs)
        return JSONResponse({"id": "chatcmpl-mock", "model": kwargs["body"]["model"]}, status_code=200)

    def fake_allow(_ctx):
        return PolicyDecision(action=PolicyAction.ALLOW, source="test")

    def fake_resolve(**kwargs):
        # anthropic default for balanced tier — mirrors what primitives return
        return "anthropic", "claude-sonnet-4-6", "test-resolver"

    def fake_resolve_openai(**kwargs):
        return "openai", "gpt-4.1", "test-resolver"

    # DB session — nothing actually reads through it (all queries are patched)
    monkeypatch.setattr(proxy_mod, "SessionLocal", lambda: MagicMock())
    monkeypatch.setattr(proxy_mod, "resolve_agent_token", lambda token, db: ("00000000-0000-0000-0000-000000000001", "user-abc"))
    monkeypatch.setattr(proxy_mod, "token_is_expired", lambda token, db: False)
    monkeypatch.setattr(proxy_mod, "set_workspace_rls", lambda db, ws: None)
    monkeypatch.setattr("app.guard.policy.evaluate_composed", fake_allow)
    monkeypatch.setattr(proxy_mod, "_upstream_url", lambda db, ws, prov, env: "http://mock-upstream")
    monkeypatch.setattr(proxy_mod, "_vault_key", lambda db, ws, prov, env: "sk-fake-vendor-key")
    monkeypatch.setattr(proxy_mod, "_upstream_api_key", lambda db, ws, env: None)
    monkeypatch.setattr(proxy_mod, "_forward", fake_forward)
    monkeypatch.setattr(proxy_mod, "_infer_ai_tool", lambda req: "test-suite")
    monkeypatch.setattr(proxy_mod, "_flatten_prompt", lambda body: "")
    monkeypatch.setattr(proxy_mod, "_estimate_input_tokens", lambda body: 10)
    monkeypatch.setattr("app.runtime.model_router.resolve_for_workspace", fake_resolve_openai)

    app = FastAPI()
    app.include_router(proxy_mod.router)
    return TestClient(app), forward_calls


def test_bare_tier_form_gets_rewritten_before_upstream(client_and_capture):
    client, forward_calls = client_and_capture
    r = client.post(
        "/proxy/openai/v1/chat/completions",
        headers={"Authorization": "Bearer guard-mt-fake"},
        json={"model": "balanced", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    assert len(forward_calls) == 1
    forwarded_body = forward_calls[0]["body"]
    # The tier form must have been rewritten to a concrete model before _forward saw it.
    assert forwarded_body["model"] == "gpt-4.1"
    # Response mirrors the resolved model
    assert r.json()["model"] == "gpt-4.1"


def test_concrete_model_passes_through_untouched(client_and_capture):
    client, forward_calls = client_and_capture
    r = client.post(
        "/proxy/openai/v1/chat/completions",
        headers={"Authorization": "Bearer guard-mt-fake"},
        json={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    forwarded_body = forward_calls[0]["body"]
    assert forwarded_body["model"] == "gpt-4.1-mini"


def test_provider_prefixed_tier_matching_endpoint(client_and_capture):
    client, forward_calls = client_and_capture
    r = client.post(
        "/proxy/openai/v1/chat/completions",
        headers={"Authorization": "Bearer guard-mt-fake"},
        json={"model": "openai/smart", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    assert forward_calls[0]["body"]["model"] == "gpt-4.1"


def test_cross_provider_prefix_forwards_raw_string(client_and_capture):
    """Endpoint provider wins — an anthropic/ prefix sent to /openai/ is
    passed through unchanged. Upstream (mocked here) would 400 in production."""
    client, forward_calls = client_and_capture
    r = client.post(
        "/proxy/openai/v1/chat/completions",
        headers={"Authorization": "Bearer guard-mt-fake"},
        json={"model": "anthropic/balanced", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    assert forward_calls[0]["body"]["model"] == "anthropic/balanced"
