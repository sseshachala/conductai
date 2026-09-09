"""Dispatch tests for /oauth/token — verify grant_type routing + rejects.

Grant handlers are mocked so we don't need DB / Clerk. The dispatcher's job
is to pick the right handler based on `grant_type` and forward the right
kwargs; each handler has its own tests where the real logic lives.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.modules.auth.oauth import token as token_mod


class _StubDb:
    pass


def test_dispatch_unknown_grant_returns_400():
    with pytest.raises(HTTPException) as exc:
        token_mod.dispatch(grant_type="password", db=_StubDb())
    assert exc.value.status_code == 400
    assert "unsupported_grant_type" in str(exc.value.detail)


def test_dispatch_authorization_code_routes_to_grant_handler(monkeypatch):
    called = {}

    def fake_handle(**kwargs):
        called.update(kwargs)
        return {"access_token": "at", "refresh_token": "rt"}

    monkeypatch.setattr(token_mod._grant_ac, "handle", fake_handle)

    out = token_mod.dispatch(
        grant_type="authorization_code",
        code="c",
        code_verifier="v",
        client_id="cid",
        redirect_uri="uri",
        db=_StubDb(),
    )
    assert out["access_token"] == "at"
    assert called["code"] == "c"
    assert called["code_verifier"] == "v"
    assert called["client_id"] == "cid"
    assert called["redirect_uri"] == "uri"


def test_dispatch_refresh_routes_to_grant_handler(monkeypatch):
    called = {}

    def fake_handle(**kwargs):
        called.update(kwargs)
        return {"access_token": "at2"}

    monkeypatch.setattr(token_mod._grant_rt, "handle", fake_handle)
    out = token_mod.dispatch(
        grant_type="refresh_token",
        refresh_token="cond_ref_abc",
        db=_StubDb(),
    )
    assert out["access_token"] == "at2"
    assert called["refresh_token"] == "cond_ref_abc"


def test_dispatch_token_exchange_requires_all_params():
    with pytest.raises(HTTPException) as exc:
        token_mod.dispatch(
            grant_type="urn:ietf:params:oauth:grant-type:token-exchange",
            db=_StubDb(),
        )
    assert exc.value.status_code == 400


def test_dispatch_token_exchange_routes_when_complete(monkeypatch):
    called = {}

    def fake_handle(**kwargs):
        called.update(kwargs)
        return {"access_token": "at3"}

    monkeypatch.setattr(token_mod._grant_te, "handle", fake_handle)
    out = token_mod.dispatch(
        grant_type="urn:ietf:params:oauth:grant-type:token-exchange",
        subject_token="jwt",
        subject_token_type="urn:ietf:params:oauth:token-type:jwt",
        resource="ws-uuid",
        db=_StubDb(),
    )
    assert out["access_token"] == "at3"
    assert called["subject_token"] == "jwt"
    assert called["resource"] == "ws-uuid"
