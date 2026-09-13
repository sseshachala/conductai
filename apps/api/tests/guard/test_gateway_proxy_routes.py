import json

import pytest

from app.modules.guard.routers import gateway_proxy
from app.modules.guard.routers import proxy as legacy_proxy


class _Request:
    pass


class _Background:
    pass


def test_parallel_gateway_proxy_routes_are_registered():
    paths = {route.path for route in gateway_proxy.router.routes}
    assert "/gateway/v1/anthropic/v1/messages" in paths
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


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("handler", "provider", "upstream_path", "auth_header_in", "auth_header_out", "bearer"),
    [
        (gateway_proxy.gateway_anthropic, "anthropic", "/v1/messages", "x-api-key", "x-api-key", False),
        (gateway_proxy.gateway_openai, "openai", "/v1/chat/completions", "authorization", "authorization", True),
        (gateway_proxy.gateway_openai_responses, "openai", "/v1/responses", "authorization", "authorization", True),
        (gateway_proxy.gateway_perplexity, "perplexity", "/chat/completions", "authorization", "authorization", True),
    ],
)
async def test_gateway_route_contract(monkeypatch, handler, provider, upstream_path, auth_header_in, auth_header_out, bearer):
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
                **({"bearer": True} if bearer else {}),
            },
        )
    ]
