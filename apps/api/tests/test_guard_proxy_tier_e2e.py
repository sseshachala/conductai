"""E2E TestClient integration for the Guard proxy tier-form path.

Verifies POST /proxy/openai/v1/chat/completions with model="balanced"
rewrites body["model"] to a concrete ID before the upstream forward.

Auth, DB, policy, vault, and upstream HTTP are all patched — we\'re
proving the flow inside _proxy(), not those dependencies.
"""
from __future__ import annotations

from types import SimpleNamespace
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
    from app.modules.guard.routers import gateway_proxy
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
    monkeypatch.setattr("app.core.database.SessionLocal", lambda: MagicMock())
    monkeypatch.setattr("app.core.auth.resolve_agent_token", lambda token, db: ("00000000-0000-0000-0000-000000000001", "user-abc"))
    monkeypatch.setattr("app.core.auth.token_is_expired", lambda token, db: False)
    monkeypatch.setattr("app.core.workspace_context.set_workspace_rls", lambda db, ws: None)
    monkeypatch.setattr("app.guard.policy.evaluate_composed", fake_allow)
    monkeypatch.setattr("app.modules.guard.gateway_helpers._upstream_url", lambda db, ws, prov, env: "http://mock-upstream")
    monkeypatch.setattr("app.modules.guard.gateway_helpers._vault_key", lambda db, ws, prov, env: "sk-fake-vendor-key")
    monkeypatch.setattr("app.modules.guard.gateway_helpers._upstream_api_key", lambda db, ws, env: None)
    monkeypatch.setattr("app.guard.router.upstream", fake_forward)
    monkeypatch.setattr("app.modules.guard.gateway_helpers._infer_ai_tool", lambda req: "test-suite")
    monkeypatch.setattr("app.guard.policy.flatten_prompt", lambda body: "")
    monkeypatch.setattr("app.guard.audit._estimate_input_tokens", lambda body: 10)
    monkeypatch.setattr("app.runtime.model_router.resolve_for_workspace", fake_resolve_openai)
    monkeypatch.setattr(
        "app.modules.guard.gateway_runtime.TransportResolver.resolve",
        lambda *args, **kwargs: None,
    )

    app = FastAPI()
    app.include_router(proxy_mod.router)
    app.include_router(gateway_proxy.router)
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


def test_routing_meta_is_threaded_into_audit_args(client_and_capture):
    """When a tier-form is sent, audit_args[15] must carry the routing_meta dict
    so guard_audit_events.routing_meta gets populated by the writer."""
    client, forward_calls = client_and_capture
    r = client.post(
        "/proxy/openai/v1/chat/completions",
        headers={"Authorization": "Bearer guard-mt-fake"},
        json={"model": "balanced", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    audit_args = forward_calls[0]["audit_args"]
    assert len(audit_args) >= 16, "audit_args must include routing_meta at position 15"
    routing_meta = audit_args[15]
    assert routing_meta is not None
    assert routing_meta["tier_form"] == "balanced"
    assert routing_meta["resolved_model"] == "gpt-4.1"
    assert routing_meta["endpoint_provider"] == "openai"
    assert routing_meta["resolution_source"] == "workspace_primitives"


def test_routing_meta_is_none_for_concrete_model(client_and_capture):
    client, forward_calls = client_and_capture
    r = client.post(
        "/proxy/openai/v1/chat/completions",
        headers={"Authorization": "Bearer guard-mt-fake"},
        json={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    audit_args = forward_calls[0]["audit_args"]
    assert audit_args[15] is None, "concrete model calls must leave routing_meta NULL"


def test_anthropic_token_count_forwards_headers_and_is_non_billable(client_and_capture):
    client, forward_calls = client_and_capture
    response = client.post(
        "/gateway/v1/anthropic/v1/messages/count_tokens",
        headers={
            "Authorization": "Bearer guard-mt-fake",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "context-management-2025-06-27",
        },
        json={
            "model": "claude-sonnet-4-6",
            "messages": [{"role": "user", "content": "hello"}],
        },
    )

    assert response.status_code == 200
    call = forward_calls[0]
    assert call["path"] == "/v1/messages/count_tokens"
    assert call["extra_headers"]["anthropic-version"] == "2023-06-01"
    assert call["extra_headers"]["anthropic-beta"] == "context-management-2025-06-27"
    assert "authorization" not in call["extra_headers"]
    assert call["audit_args"][15] == {
        "operation": "token_count",
        "billable": False,
    }


def test_anthropic_token_count_requires_authentication(client_and_capture):
    client, forward_calls = client_and_capture

    response = client.post(
        "/gateway/v1/anthropic/v1/messages/count_tokens",
        json={"model": "claude-test", "messages": []},
    )

    assert response.status_code == 401
    assert forward_calls == []


def test_anthropic_token_count_preserves_upstream_error(
    client_and_capture,
    monkeypatch,
):
    from app.modules.guard.routers import proxy as proxy_mod

    client, _ = client_and_capture

    async def rejected(**kwargs):
        return JSONResponse(
            {"error": {"type": "invalid_request_error", "message": "bad model"}},
            status_code=400,
        )

    monkeypatch.setattr("app.guard.router.upstream", rejected)
    response = client.post(
        "/gateway/v1/anthropic/v1/messages/count_tokens",
        headers={"x-api-key": "guard-mt-fake"},
        json={"model": "missing-claude", "messages": []},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {"type": "invalid_request_error", "message": "bad model"}
    }


def test_anthropic_token_count_uses_profile_selected_transport(
    client_and_capture,
    monkeypatch,
):
    client, raw_forward_calls = client_and_capture
    transport_calls = []

    class _ProfileTransport:
        async def forward(self, **kwargs):
            transport_calls.append(kwargs)
            return JSONResponse({"input_tokens": 4}, status_code=200)

    runtime = SimpleNamespace(
        upstream_url="https://litellm.test/v1",
        api_key="litellm-vault-key",
        transport=_ProfileTransport(),
        profile=SimpleNamespace(provider="litellm"),
    )
    monkeypatch.setattr(
        "app.modules.guard.gateway_runtime.TransportResolver.resolve",
        lambda *args, **kwargs: runtime,
    )

    response = client.post(
        "/gateway/v1/anthropic/v1/messages/count_tokens",
        headers={"x-api-key": "guard-mt-fake"},
        json={"model": "claude-test", "messages": []},
    )

    assert response.status_code == 200
    assert response.json() == {"input_tokens": 4}
    assert raw_forward_calls == []
    assert transport_calls[0]["upstream"] == "https://litellm.test/v1"
    assert transport_calls[0]["real_key"] == "litellm-vault-key"
