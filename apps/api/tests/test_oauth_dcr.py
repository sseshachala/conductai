"""RFC 7591 Dynamic Client Registration — /oauth/register.

Unit-level: exercise the handler directly with an in-memory stub session so
we don't need Postgres to run these. The handler only calls .add + .commit
on the session — mock covers it.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.modules.auth.oauth import dcr


class _StubSession:
    def __init__(self):
        self.added = []
        self.committed = False

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        self.committed = True


def _req(**overrides):
    base = dict(
        client_name="Claude Desktop",
        redirect_uris=["https://claude.ai/oauth/callback"],
    )
    base.update(overrides)
    return dcr.RegisterRequest(**base)


def test_register_happy_path():
    db = _StubSession()
    result = dcr.register_client(_req(), db)
    assert result["client_id"].startswith(dcr._CLIENT_ID_PREFIX)
    assert result["client_name"] == "Claude Desktop"
    assert result["token_endpoint_auth_method"] == "none"
    assert db.committed
    assert len(db.added) == 1


def test_register_rejects_insecure_redirect_uri():
    db = _StubSession()
    with pytest.raises(HTTPException) as exc:
        dcr.register_client(_req(redirect_uris=["http://evil.example/cb"]), db)
    assert exc.value.status_code == 400
    assert "insecure_redirect_uri" in str(exc.value.detail)


def test_register_allows_localhost_http():
    db = _StubSession()
    result = dcr.register_client(_req(redirect_uris=["http://localhost:7777/cb"]), db)
    assert result["client_id"].startswith(dcr._CLIENT_ID_PREFIX)


def test_register_rejects_unknown_grant():
    db = _StubSession()
    with pytest.raises(HTTPException) as exc:
        dcr.register_client(_req(grant_types=["password"]), db)
    assert "unsupported_grant_type" in str(exc.value.detail)


def test_register_rejects_confidential_client():
    db = _StubSession()
    with pytest.raises(HTTPException) as exc:
        dcr.register_client(_req(token_endpoint_auth_method="client_secret_post"), db)
    assert "public clients" in str(exc.value.detail)


def test_register_rejects_bad_scheme():
    db = _StubSession()
    with pytest.raises(HTTPException) as exc:
        dcr.register_client(_req(redirect_uris=["ftp://foo/cb"]), db)
    assert "invalid_redirect_uri" in str(exc.value.detail)


@pytest.mark.parametrize("uri", [
    "http://localhost.evil.example/cb", "http://127.0.0.1.evil.example/cb",
    "http://localhost@evil.example/cb", "https://user:password@example.test/cb",
    "https://example.test/cb#fragment", "https://example.test:invalid/cb",
    "https://example.test/white space", "https://example.test/\\evil", "https:///cb",
])
def test_register_rejects_unsafe_redirect_without_writing(uri):
    db = _StubSession()
    with pytest.raises(HTTPException) as error:
        dcr.register_client(_req(redirect_uris=[uri]), db)
    assert error.value.status_code == 400
    assert not db.added and not db.committed


@pytest.mark.parametrize("uri", [
    "http://localhost:7777/cb", "http://127.0.0.1:7777/cb", "http://[::1]:7777/cb",
    "https://example.test/oauth/callback", "mcp://client/callback",
])
def test_register_accepts_secure_or_loopback_redirects(uri):
    assert dcr.register_client(_req(redirect_uris=[uri]), _StubSession())["redirect_uris"] == [uri]
