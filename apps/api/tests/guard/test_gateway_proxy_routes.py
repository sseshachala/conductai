from app.main import app


def test_parallel_gateway_proxy_routes_are_registered():
    paths = {route.path for route in app.routes}
    assert "/gateway/v1/anthropic/v1/messages" in paths
    assert "/gateway/v1/openai/v1/chat/completions" in paths
    assert "/gateway/v1/perplexity/chat/completions" in paths


def test_legacy_proxy_routes_remain_registered():
    paths = {route.path for route in app.routes}
    assert "/proxy/anthropic/v1/messages" in paths
    assert "/proxy/openai/v1/chat/completions" in paths
