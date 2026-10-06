"""RFC 9728 resource metadata names the host the MCP client called (#2360).

Env comes from tests/conftest.py.
"""
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app
from app.modules.auth.oauth.deployment import issuer_url

client = TestClient(app, raise_server_exceptions=False)
ISSUER = issuer_url().rstrip("/")
_gw = urlsplit(settings.conduct_proxy_url)
GATEWAY = f"{_gw.scheme}://{_gw.netloc}"


@pytest.mark.parametrize("host,expected", [
    (urlsplit(ISSUER).netloc, ISSUER),
    (_gw.netloc, GATEWAY),
    ("evil.example", ISSUER),          # spoofed Host is never echoed
    ("testserver", ISSUER),
])
def test_resource_matches_called_host(host, expected):
    body = client.get("/.well-known/oauth-protected-resource/mcp", headers={"host": host}).json()
    assert body["resource"] == expected + "/mcp"
    assert body["authorization_servers"] == [ISSUER]  # one authorization server for both hosts


def test_unauthenticated_mcp_points_at_same_host_metadata():
    res = client.post("/mcp", json={}, headers={"host": _gw.netloc})
    assert res.status_code == 401
    assert f'resource_metadata="{GATEWAY}/.well-known/oauth-protected-resource/mcp"' in res.headers["WWW-Authenticate"]
