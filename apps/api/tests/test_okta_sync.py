"""Tests for app.routers.okta_sync — sync router and helpers.

The __main__ self-check inside okta_sync.py already covers the pure mapping
(_okta_app_to_row, _extract_next_link, _sanitize_domain). This file covers the
sync loop: pagination, owner enrichment, idempotent updates, and error paths.

No real network. urlopen is monkeypatched.
"""
from __future__ import annotations

import io
import json
import uuid
from unittest.mock import MagicMock

import pytest


def _fake_http_response(body: dict | list, *, link_header: str = ""):
    """Build an object that behaves like the context manager returned by urlopen."""
    class _Resp:
        def __init__(self, payload, link):
            self._payload = json.dumps(payload).encode("utf-8")
            self.headers = {"Link": link}
        def read(self):
            return self._payload
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
    return _Resp(body, link_header)


def _app(app_id: str, *, label: str = "Sample", status: str = "ACTIVE") -> dict:
    return {
        "id": app_id,
        "label": label,
        "name": "oidc_client",
        "status": status,
        "created": "2026-08-10T01:19:40.000Z",
        "lastUpdated": "2026-08-10T01:19:40.000Z",
        "signOnMode": "OPENID_CONNECT",
        "features": [],
        "settings": {"app": {}},
    }


def test_fetch_first_owner_extracts_username(monkeypatch):
    from app.routers import okta_sync

    def _fake_urlopen(req, timeout=None):
        assert "/api/v1/apps/APPID/users" in req.full_url
        assert req.headers["Authorization"] == "SSWS TESTTOK"
        return _fake_http_response([{"id": "u1", "credentials": {"userName": "owner@example.com"}}])

    monkeypatch.setattr(okta_sync.urllib.request, "urlopen", _fake_urlopen)
    assert okta_sync._fetch_first_owner("x.okta.com", "TESTTOK", "APPID") == "owner@example.com"


def test_fetch_first_owner_falls_back_to_id_when_username_missing(monkeypatch):
    from app.routers import okta_sync

    monkeypatch.setattr(
        okta_sync.urllib.request,
        "urlopen",
        lambda req, timeout=None: _fake_http_response([{"id": "0uxABC", "credentials": {}}]),
    )
    assert okta_sync._fetch_first_owner("x.okta.com", "T", "A") == "0uxABC"


def test_fetch_first_owner_returns_none_on_empty(monkeypatch):
    from app.routers import okta_sync
    monkeypatch.setattr(
        okta_sync.urllib.request,
        "urlopen",
        lambda req, timeout=None: _fake_http_response([]),
    )
    assert okta_sync._fetch_first_owner("x.okta.com", "T", "A") is None


def test_fetch_first_owner_returns_none_on_network_error(monkeypatch):
    from app.routers import okta_sync

    def _boom(req, timeout=None):
        raise ConnectionError("network down")

    monkeypatch.setattr(okta_sync.urllib.request, "urlopen", _boom)
    assert okta_sync._fetch_first_owner("x.okta.com", "T", "A") is None


def test_extract_next_link_prefers_rel_next():
    from app.routers.okta_sync import _extract_next_link
    link = (
        '<https://x.okta.com/api/v1/apps?after=abc>; rel="next", '
        '<https://x.okta.com/api/v1/apps>; rel="self"'
    )
    assert _extract_next_link(link) == "https://x.okta.com/api/v1/apps?after=abc"


def test_extract_next_link_returns_none_when_no_next():
    from app.routers.okta_sync import _extract_next_link
    assert _extract_next_link('<https://x.okta.com/apps>; rel="self"') is None
    assert _extract_next_link("") is None


def test_okta_app_to_row_deactivated_populates_deactivated_at():
    from app.routers.okta_sync import _okta_app_to_row
    r = _okta_app_to_row(_app("id-1", status="INACTIVE"))
    assert r["lifecycle_state"] == "deactivated"
    assert r["deactivated_at"] is not None


def test_okta_app_to_row_maps_deleted_to_expired():
    from app.routers.okta_sync import _okta_app_to_row
    r = _okta_app_to_row(_app("id-2", status="DELETED"))
    assert r["lifecycle_state"] == "expired"


def test_okta_app_to_row_defaults_platform_to_name_when_no_agent_hint():
    from app.routers.okta_sync import _okta_app_to_row
    r = _okta_app_to_row(_app("id-3"))
    assert r["platform_of_origin"] == "oidc_client"


def test_okta_app_to_row_prefers_agent_platform_hint():
    from app.routers.okta_sync import _okta_app_to_row
    app = _app("id-4")
    app["settings"] = {"app": {"agent_platform": "Claude Enterprise"}}
    r = _okta_app_to_row(app)
    assert r["platform_of_origin"] == "claude enterprise"


def test_okta_app_to_row_name_truncated_to_100_chars():
    from app.routers.okta_sync import _okta_app_to_row
    r = _okta_app_to_row(_app("id-5", label="x" * 500))
    assert len(r["name"]) == 100


def test_sanitize_domain_strips_scheme_and_trailing_slash():
    from app.routers.okta_sync import _sanitize_domain
    assert _sanitize_domain("https://foo.okta.com/") == "foo.okta.com"
    assert _sanitize_domain("http://foo.okta.com") == "foo.okta.com"
    assert _sanitize_domain("foo.okta.com") == "foo.okta.com"
    assert _sanitize_domain("") == ""


# ─── Idempotency: rerun updates existing rows in place ─────────────────────

def test_sync_updates_existing_identity_not_duplicate(monkeypatch):
    """Second sync of the same Okta app id must call db.add zero times for
    that row — the update path mutates the existing SQLAlchemy object."""
    from app.routers import okta_sync

    existing = MagicMock()
    existing.owner_user_id = "prior-owner@example.com"
    existing.lifecycle_state = "active"

    db = MagicMock()
    # First .query() → Integration (return None: no stored config)
    # Second .query() (loop) → AgentIdentity (return the existing row)
    integration_q = MagicMock()
    integration_q.filter.return_value.first.return_value = None
    ai_q = MagicMock()
    ai_q.filter.return_value.first.return_value = existing
    db.query.side_effect = [integration_q, ai_q]

    # Fake pagination: one page, no next link
    monkeypatch.setattr(
        okta_sync.urllib.request,
        "urlopen",
        lambda req, timeout=None: _fake_http_response([_app("APPID")]),
    )
    monkeypatch.setattr(okta_sync, "_fetch_first_owner", lambda d, t, a: "new-owner@example.com")

    body = okta_sync.OktaSyncRequest(domain="x.okta.com", token="TOK", limit=100)
    resp = okta_sync.sync_okta(
        workspace_id=str(uuid.uuid4()),
        body=body,
        _ws="ignored",
        _="admin",
        db=db,
    )
    assert resp.updated == 1
    assert resp.imported == 0
    # No new row was added for this app id
    add_calls = [c for c in db.method_calls if c[0] == "add"]
    assert len(add_calls) == 0
    # Existing owner must be preserved (owner_user_id was already set)
    assert existing.owner_user_id == "prior-owner@example.com"


def test_sync_requires_domain_and_token():
    from fastapi import HTTPException
    from app.routers import okta_sync

    # No stored config, empty body → 422
    db = MagicMock()
    integration_q = MagicMock()
    integration_q.filter.return_value.first.return_value = None
    db.query.return_value = integration_q

    with pytest.raises(HTTPException) as ei:
        okta_sync.sync_okta(
            workspace_id=str(uuid.uuid4()),
            body=okta_sync.OktaSyncRequest(),
            _ws="x", _="admin", db=db,
        )
    assert ei.value.status_code == 422


def test_sync_okta_502_when_api_errors(monkeypatch):
    import urllib.error
    from fastapi import HTTPException
    from app.routers import okta_sync

    def _http_boom(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, None)

    monkeypatch.setattr(okta_sync.urllib.request, "urlopen", _http_boom)

    db = MagicMock()
    integration_q = MagicMock()
    integration_q.filter.return_value.first.return_value = None
    db.query.return_value = integration_q

    with pytest.raises(HTTPException) as ei:
        okta_sync.sync_okta(
            workspace_id=str(uuid.uuid4()),
            body=okta_sync.OktaSyncRequest(domain="x.okta.com", token="TOK"),
            _ws="x", _="admin", db=db,
        )
    assert ei.value.status_code == 502


if __name__ == "__main__":
    # Smallest possible smoke: mapping self-check exists in the router itself.
    # Run pytest for the full suite.
    import subprocess, sys
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))
