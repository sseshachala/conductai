import json
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.modules.guard.routers import gateway_proxy
from app.modules.guard.routers import proxy as legacy_proxy


class _Request:
    pass


class _Background:
    pass


def test_parallel_gateway_proxy_routes_are_registered():
    paths = {route.path for route in gateway_proxy.router.routes}
    assert "/gateway/v1/anthropic/v1/messages" in paths
    assert "/gateway/v1/anthropic/v1/messages/count_tokens" in paths
    assert "/gateway/v1/anthropic/v1/models" in paths
    assert "/gateway/v1/anthropic/api/hello" in paths
    assert "/gateway/v1/openai/v1/models" in paths
    assert "/gateway/v1/openai/v1/chat/completions" in paths
    assert "/gateway/v1/openai/v1/responses" in paths
    assert "/gateway/v1/perplexity/chat/completions" in paths


def test_gateway_openai_models_requires_workspace_authentication():
    route = next(
        route
        for route in gateway_proxy.router.routes
        if route.path == "/gateway/v1/openai/v1/models"
    )
    assert any(
        dependency.call is gateway_proxy.get_workspace_id
        for dependency in route.dependant.dependencies
    )


def test_gateway_anthropic_models_requires_gateway_authentication():
    route = next(
        route
        for route in gateway_proxy.router.routes
        if route.path == "/gateway/v1/anthropic/v1/models"
    )

    assert any(
        dependency.call is gateway_proxy._gateway_principal
        for dependency in route.dependant.dependencies
    )


def test_gateway_anthropic_models_returns_401_without_credentials():
    app = FastAPI()
    app.include_router(gateway_proxy.router)
    app.dependency_overrides[gateway_proxy.get_db] = lambda: object()

    response = TestClient(app).get("/gateway/v1/anthropic/v1/models?limit=1000")

    assert response.status_code == 401


def test_legacy_proxy_routes_remain_registered():
    paths = {route.path for route in legacy_proxy.router.routes}
    assert "/proxy/anthropic/v1/messages" in paths
    assert "/proxy/openai/v1/chat/completions" in paths
    assert "/proxy/openai/v1/responses" not in paths


@pytest.mark.anyio
async def test_gateway_openai_models_uses_codex_bundled_catalog():
    response = await gateway_proxy.gateway_openai_models("workspace-test")

    assert response.status_code == 200
    assert json.loads(response.body) == {"models": []}
    assert response.headers["cache-control"] == "private, max-age=300"


def _request(headers: dict[str, str] | None = None) -> Request:
    encoded = [
        (key.lower().encode(), value.encode())
        for key, value in (headers or {}).items()
    ]
    return Request({"type": "http", "method": "GET", "path": "/", "headers": encoded})


def test_gateway_principal_accepts_claude_api_key(monkeypatch):
    monkeypatch.setattr(
        gateway_proxy,
        "resolve_agent_token",
        lambda token, db: (
            ("workspace-test", "user-test")
            if token == "cond_agt_test"
            else None
        ),
    )
    monkeypatch.setattr(gateway_proxy, "set_workspace_rls", lambda db, workspace: None)

    principal = gateway_proxy._gateway_principal(
        _request({"x-api-key": "cond_agt_test"}),
        object(),
    )

    assert principal == ("workspace-test", "user-test")


def test_gateway_principal_requires_a_credential():
    with pytest.raises(HTTPException) as exc:
        gateway_proxy._gateway_principal(_request(), object())

    assert exc.value.status_code == 401


def test_gateway_principal_rejects_cross_workspace_header(monkeypatch):
    monkeypatch.setattr(
        gateway_proxy,
        "resolve_agent_token",
        lambda token, db: ("workspace-a", "user-test"),
    )

    with pytest.raises(HTTPException) as exc:
        gateway_proxy._gateway_principal(
            _request(
                {
                    "authorization": "Bearer cond_agt_test",
                    "x-conductai-workspace-id": "workspace-b",
                }
            ),
            object(),
        )

    assert exc.value.status_code == 403


@pytest.mark.anyio
async def test_gateway_anthropic_models_are_limited_to_profile_deployments(monkeypatch):
    profile = SimpleNamespace(
        deployments=[
            SimpleNamespace(alias="sonnet", model="anthropic/claude-sonnet-4-6"),
            SimpleNamespace(alias="sonnet-copy", model="anthropic/claude-sonnet-4-6"),
            SimpleNamespace(alias="opus", model="claude-opus-4-6"),
        ]
    )

    class _Resolver:
        def resolve_profile(self, db, workspace_id, provider, environment_id):
            assert workspace_id == "workspace-test"
            assert provider == "anthropic"
            assert environment_id == "environment-test"
            return profile

    monkeypatch.setattr(gateway_proxy, "TransportResolver", _Resolver)
    background = BackgroundTasks()
    response = await gateway_proxy.gateway_anthropic_models(
        _request({"x-conductai-environment-id": "environment-test"}),
        background,
        1000,
        ("workspace-test", "user-test"),
        object(),
    )

    assert json.loads(response.body) == {
        "data": [
            {"id": "anthropic/claude-sonnet-4-6", "display_name": "sonnet"},
            {"id": "claude-opus-4-6", "display_name": "opus"},
        ]
    }
    assert response.headers["cache-control"] == "private, max-age=300"
    assert len(background.tasks) == 1
    assert background.tasks[0].kwargs["routing_meta"] == {
        "operation": "model_catalog",
        "billable": False,
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    (
        "handler",
        "provider",
        "upstream_path",
        "auth_header_in",
        "auth_header_out",
        "extra",
    ),
    [
        (
            gateway_proxy.gateway_anthropic,
            "anthropic",
            "/v1/messages",
            "x-api-key",
            "x-api-key",
            {"auth_header_fallback": "authorization"},
        ),
        (
            gateway_proxy.gateway_anthropic_count_tokens,
            "anthropic",
            "/v1/messages/count_tokens",
            "x-api-key",
            "x-api-key",
            {"auth_header_fallback": "authorization", "operation": "token_count"},
        ),
        (
            gateway_proxy.gateway_openai,
            "openai",
            "/v1/chat/completions",
            "authorization",
            "authorization",
            {"bearer": True},
        ),
        (
            gateway_proxy.gateway_openai_responses,
            "openai",
            "/v1/responses",
            "authorization",
            "authorization",
            {"bearer": True},
        ),
        (
            gateway_proxy.gateway_perplexity,
            "perplexity",
            "/chat/completions",
            "authorization",
            "authorization",
            {"bearer": True},
        ),
    ],
)
async def test_gateway_route_contract(
    monkeypatch,
    handler,
    provider,
    upstream_path,
    auth_header_in,
    auth_header_out,
    extra,
):
    calls = []

    async def fake_proxy(request, background, **kwargs):
        calls.append((request, background, kwargs))
        return {"ok": True}

    monkeypatch.setattr(gateway_proxy, "_proxy", fake_proxy)
    request = _Request()
    background = _Background()
    result = await handler(request, background)

    assert result == {"ok": True}
    assert calls == [
        (
            request,
            background,
            {
                "provider": provider,
                "upstream_path": upstream_path,
                "auth_header_in": auth_header_in,
                "auth_header_out": auth_header_out,
                "canonical_profile": True,
                **extra,
            },
        )
    ]
