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
def approved_client_gateway(client_and_capture, monkeypatch):
    from uuid import uuid4
    from unittest.mock import AsyncMock
    from app.core.config import settings
    from app.modules.guard import gateway_handler, gateway_model_selection

    monkeypatch.setattr(settings, "guard_gateway_profile_v2", True)
    monkeypatch.setattr(settings, "guard_gateway_profile_v2_rollout_pct", 100)
    monkeypatch.setattr("app.runtime.model_router.resolve_for_workspace",
                        lambda *a, **kw: ("openai", "gpt-first", "workspace tier"))
    rows = []
    for code, model, provider, operation in [
        ("aaaaaaaa", "gpt-first", "openai", "openai_responses"),
        ("bbbbbbbb", "gpt-second", "openai", "openai_responses"),
        ("cccccccc", "claude-test", "anthropic", "anthropic_messages"),
    ]:
        rows.append((SimpleNamespace(cond_code=code), SimpleNamespace(id=uuid4(), snapshot={
            "name": model, "model_alias": "Second Model" if model == "gpt-second" else model, "accepts": [operation],
            "targets": [{"id": "primary", "transport": "native_http", "provider": provider,
                         "model": model, "credential_ref": "vault://11111111-1111-4111-8111-111111111111/test-key"}],
        })))
    db = MagicMock()
    query = db.query.return_value
    query.join.return_value = query
    query.filter.return_value = query
    query.all.return_value = rows

    def select(workspace, requested, provider, path):
        from app.runtime.gateway_v2_bridge import map_operation
        return gateway_model_selection.select_model(db, workspace, requested, map_operation(provider, path))
    monkeypatch.setattr(gateway_model_selection, "select_model_owned", select)
    for name in ("build_credential_resolver", "build_vendor_credential_resolver"):
        monkeypatch.setattr("app.runtime.gateway_v2_bridge." + name, lambda *a, **kw: lambda *a: "test-key")
    monkeypatch.setattr(gateway_handler, "_build_v2_plan_owned",
                        lambda **kw: gateway_handler._build_v2_plan(db=db, **kw))
    dispatched = []
    async def execute(**kwargs):
        dispatched.append(kwargs)
        if kwargs["stream"]:
            from fastapi.responses import StreamingResponse
            async def chunks():
                yield b'data: {"type":"response.completed","response":{"usage":{"input_tokens":1,"output_tokens":1}}}\n\n'
            return StreamingResponse(chunks(), media_type="text/event-stream")
        return JSONResponse({"output": [], "usage": {"input_tokens": 1, "output_tokens": 1}})
    monkeypatch.setattr(gateway_handler, "_execute_v2", execute)
    opened = AsyncMock(return_value=SimpleNamespace(fail_response=None, row_id=None, request_id="test-request"))
    monkeypatch.setattr("app.modules.guard.gateway_lifecycle.open_durable_row", opened)
    monkeypatch.setattr("app.modules.guard.gateway_lifecycle.close_durable_row", AsyncMock())
    monkeypatch.setattr("app.modules.guard.gateway_lifecycle.finalize_durable_row", AsyncMock())
    return client_and_capture[0], dispatched, opened


@pytest.mark.parametrize("provider,path,models", [
    ("openai", "/v1/responses", ["gpt-first", "gpt-second", "balanced"]),
    ("anthropic", "/v1/messages", ["claude-test"]),
])
@pytest.mark.parametrize("stream", [False, True])
def test_approved_client_models_preserve_tools_stream_and_audit(approved_client_gateway, provider, path, models, stream):
    client, dispatched, opened = approved_client_gateway
    tools = [{"type": "function", "name": "lookup", "parameters": {"type": "object"}}]
    for model in models:
        response = client.post(f"/gateway/v1/{provider}{path}",
            headers={"Authorization": "Bearer guard-mt-fake"},
            json={"model": model, "input": "hello", "messages": [{"role": "user", "content": "hello"}],
                  "tools": tools, "stream": stream, "max_tokens": 10})
        assert response.status_code == 200, response.text
        assert dispatched[-1]["stream"] is stream
        assert dispatched[-1]["body"]["tools"] == tools
        target_model = "gpt-first" if model == "balanced" else model
        assert dispatched[-1]["plan"].resolved.profile.targets[0].model == target_model
        metadata = opened.call_args.kwargs["routing_meta"]
        assert metadata["requested_model"] == model
        assert metadata["revision_id"] == str(dispatched[-1]["plan"].resolved.revision_id)
        assert opened.call_args.kwargs["clerk_user_id"] == "user-abc"


def test_unpublished_client_model_never_dispatches(approved_client_gateway):
    client, dispatched, _ = approved_client_gateway
    response = client.post("/gateway/v1/openai/v1/responses", headers={"Authorization": "Bearer guard-mt-fake"},
                           json={"model": "unpublished", "input": "hello"})
    assert response.status_code == 404
    assert not dispatched


def test_approved_profile_still_subject_to_policy(approved_client_gateway, monkeypatch):
    client, dispatched, _ = approved_client_gateway
    monkeypatch.setattr("app.guard.policy.evaluate_composed",
                        lambda ctx: PolicyDecision(action=PolicyAction.BLOCK, source="test"))
    response = client.post("/gateway/v1/openai/v1/responses", headers={"Authorization": "Bearer guard-mt-fake"},
                           json={"model": "gpt-first", "input": "hello"})
    assert response.status_code == 403, response.text
    assert not dispatched


@pytest.fixture
def client_and_capture(monkeypatch):
    # This routing fixture has no configured rate limits or live Redis dependency.
    monkeypatch.setattr("app.modules.guard.rate_limit._resolve_limits", lambda *a: (None, None, "none"))
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
    monkeypatch.setattr("app.guard.audit._estimate_input_tokens_bounded", lambda body: 10)
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


@pytest.mark.parametrize("provider,path,model", [
    ("openai", "/v1/responses", "gpt-4.1"),
    ("openai", "/v1/chat/completions", "gpt-4.1"),
    ("anthropic", "/v1/messages", "claude-sonnet-4-6"),
])
def test_gateway_preserves_usage_protocol_for_audit(client_and_capture, provider, path, model):
    client, forward_calls = client_and_capture
    response = client.post(
        f"/gateway/v1/{provider}{path}",
        headers={"Authorization": "Bearer guard-mt-fake"},
        json={"model": model, "messages": [{"role": "user", "content": "hi"}],
              "input": "hi", "max_tokens": 5},
    )
    assert response.status_code == 200, response.text
    assert forward_calls[0]["audit_args"][15]["operation"] == path


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


def test_concrete_model_retains_operation_without_tier_metadata(client_and_capture):
    client, forward_calls = client_and_capture
    r = client.post(
        "/proxy/openai/v1/chat/completions",
        headers={"Authorization": "Bearer guard-mt-fake"},
        json={"model": "gpt-4.1-mini", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 200, r.text
    audit_args = forward_calls[0]["audit_args"]
    assert audit_args[15] == {"operation": "/v1/chat/completions"}


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
