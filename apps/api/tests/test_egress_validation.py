"""Outbound URL validation (app.core.egress) and its call sites."""
from __future__ import annotations

import socket
from unittest.mock import MagicMock, patch

import pytest

from app.core import egress
from app.core.egress import EgressBlocked, validate_outbound_url


def _gai(*addrs):
    def fake(host, port, *a, **k):
        return [
            (socket.AF_INET6 if ":" in ip else socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 443))
            for ip in addrs
        ]
    return fake


@pytest.fixture(autouse=True)
def _prod_env(monkeypatch):
    monkeypatch.setattr(egress.settings, "environment", "production")
    monkeypatch.setattr(egress.settings, "egress_allowed_hosts", [])


def test_public_host_allowed(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _gai("93.184.216.34"))
    assert validate_outbound_url("https://example.com/hook") == ["93.184.216.34"]


BAD_IPS = [
    "10.0.0.5", "192.168.1.1", "172.16.0.1", "127.0.0.1", "::1", "169.254.169.254",
    "169.254.10.10", "fe80::1", "fd00:ec2::254", "100.64.0.1", "0.0.0.0",
    "224.0.0.1", "ff02::1", "240.0.0.1", "::ffff:127.0.0.1", "::ffff:10.0.0.1",
    "::ffff:169.254.169.254",
]


@pytest.mark.parametrize("ip", BAD_IPS)
def test_literal_ips_rejected(ip):
    host = f"[{ip}]" if ":" in ip else ip
    with pytest.raises(EgressBlocked):
        validate_outbound_url(f"https://{host}/x")


@pytest.mark.parametrize("ip", BAD_IPS)
def test_dns_name_resolving_to_blocked_rejected(monkeypatch, ip):
    monkeypatch.setattr(socket, "getaddrinfo", _gai(ip))
    with pytest.raises(EgressBlocked):
        validate_outbound_url("https://host.example.com/x")


def test_any_blocked_address_rejects(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _gai("93.184.216.34", "10.0.0.1"))
    with pytest.raises(EgressBlocked):
        validate_outbound_url("https://mixed.example.com")


def test_http_rejected_in_production_allowed_in_dev(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _gai("93.184.216.34"))
    with pytest.raises(EgressBlocked):
        validate_outbound_url("http://example.com")
    monkeypatch.setattr(egress.settings, "environment", "development")
    assert validate_outbound_url("http://example.com")
    with pytest.raises(EgressBlocked):
        validate_outbound_url("ftp://example.com")


def test_unresolvable_fails_closed_unless_opted_in(monkeypatch):
    def boom(*a, **k):
        raise socket.gaierror("nope")
    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(EgressBlocked):
        validate_outbound_url("https://nx.example.com")
    assert validate_outbound_url("https://nx.example.com", allow_unresolvable=True) == []


def test_allowlisted_host_allowed(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _gai("10.1.2.3"))
    with pytest.raises(EgressBlocked):
        validate_outbound_url("https://llm.corp.internal/v1")
    monkeypatch.setattr(egress.settings, "egress_allowed_hosts", ["LLM.corp.internal"])
    assert validate_outbound_url("https://llm.corp.internal/v1") == ["10.1.2.3"]
    # allowlist is per-host, not global
    with pytest.raises(EgressBlocked):
        validate_outbound_url("https://other.corp.internal/v1")


# -- output_block ------------------------------------------------------------

def _webhook_block(url):
    return {"data": {"integration": "webhook", "config": {"webhook_url": url}}}


def test_output_block_rejects_private_webhook(monkeypatch):
    from app.runtime.blocks.output_block import _execute_output
    monkeypatch.setattr(socket, "getaddrinfo", _gai("169.254.169.254"))
    with patch("httpx.post") as post:
        out = _execute_output(_webhook_block("https://{{hook.host}}/x"), {"hook": {"host": "meta.example.com"}})
    assert out["sent"] is False and "rejected" in out["error"]
    post.assert_not_called()


def test_output_block_public_webhook_does_not_follow_redirects(monkeypatch):
    from app.runtime.blocks.output_block import _execute_output
    monkeypatch.setattr(socket, "getaddrinfo", _gai("93.184.216.34"))
    resp = MagicMock(status_code=302)
    with patch("httpx.post", return_value=resp) as post:
        out = _execute_output(_webhook_block("https://example.com/hook"), {})
    assert out["sent"] is True
    assert post.call_args.kwargs["follow_redirects"] is False


# -- gateway -----------------------------------------------------------------

def test_legacy_llm_upstream_private_rejected(monkeypatch):
    from app.modules.guard import gateway_helpers as gh
    monkeypatch.setattr(socket, "getaddrinfo", _gai("127.0.0.1"))
    monkeypatch.setattr("app.core.credentials.get_credential", lambda *a, **k: {"LLM_UPSTREAM": "https://llm.example.com/v1"})
    with pytest.raises(gh.UpstreamURLRejected):
        gh._upstream_url(MagicMock(), "ws", "openai", "env1")


def test_legacy_llm_upstream_public_ok(monkeypatch):
    from app.modules.guard import gateway_helpers as gh
    monkeypatch.setattr(socket, "getaddrinfo", _gai("93.184.216.34"))
    monkeypatch.setattr("app.core.credentials.get_credential", lambda *a, **k: {"LLM_UPSTREAM": "https://llm.example.com/v1/"})
    assert gh._upstream_url(MagicMock(), "ws", "openai", "env1") == "https://llm.example.com/v1"


def test_v2_profile_endpoint_uses_shared_validator(monkeypatch):
    from app.modules.guard.gateway_config import _reject_private_endpoint
    monkeypatch.setattr(socket, "getaddrinfo", _gai("10.0.0.9"))
    with pytest.raises(ValueError):
        _reject_private_endpoint("https://azure.example.com")
    with pytest.raises(ValueError):
        _reject_private_endpoint("https://[::ffff:127.0.0.1]/v1")


def test_allowlisted_host_may_use_http_in_production(monkeypatch):
    # In-cluster model services (on-prem) are usually plain http.
    monkeypatch.setattr(socket, "getaddrinfo", _gai("10.42.0.7"))
    monkeypatch.setattr(egress.settings, "egress_allowed_hosts", ["litellm.ai.svc.cluster.local"])
    assert validate_outbound_url("http://litellm.ai.svc.cluster.local:4000/v1") == ["10.42.0.7"]
    # a non-allowlisted public host still needs https
    monkeypatch.setattr(socket, "getaddrinfo", _gai("93.184.216.34"))
    with pytest.raises(EgressBlocked, match="https"):
        validate_outbound_url("http://example.com/v1")
