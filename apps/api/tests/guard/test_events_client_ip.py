"""Unit tests for events.py _client_ip_from (audit S12 follow-up to #1790).

The old code trusted the first X-Forwarded-For value blindly, letting a
caller forge the IP recorded on their own session rows. New behaviour:
XFF is ignored unless TRUSTED_PROXY_CIDRS is configured, and when it is
we walk from the rightmost hop and take the first non-trusted address.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch


def _mk_request(*, xff: str | None, client_host: str):
    headers = {"x-forwarded-for": xff} if xff else {}
    return SimpleNamespace(
        headers=headers,
        client=SimpleNamespace(host=client_host),
    )


def test_client_ip_ignores_xff_without_trusted_cidrs():
    from app.modules.guard.routers import events
    with patch.object(events, "settings", SimpleNamespace(trusted_proxy_cidrs="")):
        req = _mk_request(xff="1.2.3.4, 5.6.7.8", client_host="10.0.0.5")
        assert events._client_ip_from(req) == "10.0.0.5"


def test_client_ip_walks_xff_from_right_when_trusted_cidrs_set():
    from app.modules.guard.routers import events
    with patch.object(events, "settings", SimpleNamespace(trusted_proxy_cidrs="10.0.0.0/8")):
        req = _mk_request(xff="1.2.3.4, 10.0.0.5, 10.0.0.6", client_host="10.0.0.6")
        assert events._client_ip_from(req) == "1.2.3.4"


def test_client_ip_ignores_malformed_xff_hop():
    from app.modules.guard.routers import events
    with patch.object(events, "settings", SimpleNamespace(trusted_proxy_cidrs="10.0.0.0/8")):
        req = _mk_request(xff="1.2.3.4, not-an-ip, 10.0.0.5", client_host="10.0.0.5")
        assert events._client_ip_from(req) == "1.2.3.4"


def test_client_ip_falls_back_when_xff_missing():
    from app.modules.guard.routers import events
    with patch.object(events, "settings", SimpleNamespace(trusted_proxy_cidrs="10.0.0.0/8")):
        req = _mk_request(xff=None, client_host="203.0.113.5")
        assert events._client_ip_from(req) == "203.0.113.5"
