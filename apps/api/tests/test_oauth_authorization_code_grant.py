"""authorization_code grant validation — reject-path tests via stubbed DB.

The happy path mints tokens through `_upsert_identity` which requires the
real Postgres tables, so it belongs in the nightly matrix job. Here we cover
the guards that are pure logic on the row: status, expiry, PKCE, redirect_uri,
client_id, missing identity binding.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.modules.auth.oauth.grants import authorization_code as grant


class _StubDb:
    def __init__(self, row):
        self._row = row
        self.committed = 0

    def query(self, _model):
        return self

    def filter(self, *_a, **_k):
        return self

    def first(self):
        return self._row

    def commit(self):
        self.committed += 1


def _make_row(**overrides):
    now = datetime.now(timezone.utc)
    row = SimpleNamespace(
        code_hash=hashlib.sha256(b"raw").hexdigest(),
        client_id="cid-1",
        redirect_uri="https://x/cb",
        code_challenge="ignored",
        code_challenge_method="S256",
        status="issued",
        expires_at=now + timedelta(seconds=30),
        clerk_user_id="user_1",
        workspace_id="00000000-0000-0000-0000-000000000000",
        scope=None,
        used_at=None,
    )
    for k, v in overrides.items():
        setattr(row, k, v)
    return row


def _call(row, **kwargs):
    defaults = dict(
        code="raw",
        code_verifier="v",
        client_id="cid-1",
        redirect_uri="https://x/cb",
    )
    defaults.update(kwargs)
    return grant.handle(db=_StubDb(row), **defaults)


def test_rejects_unknown_code():
    with pytest.raises(HTTPException) as exc:
        _call(None)
    assert exc.value.status_code == 400
    assert "code not recognized" in str(exc.value.detail)


def test_rejects_consumed_code():
    with pytest.raises(HTTPException) as exc:
        _call(_make_row(status="consumed"))
    assert "consumed" in str(exc.value.detail)


def test_rejects_pending_code():
    with pytest.raises(HTTPException) as exc:
        _call(_make_row(status="pending"))
    assert "pending" in str(exc.value.detail)


def test_rejects_expired_code():
    past = datetime.now(timezone.utc) - timedelta(seconds=5)
    with pytest.raises(HTTPException) as exc:
        _call(_make_row(expires_at=past))
    assert "expired" in str(exc.value.detail)


def test_rejects_client_id_mismatch():
    with pytest.raises(HTTPException) as exc:
        _call(_make_row(), client_id="different")
    assert "client_id mismatch" in str(exc.value.detail)


def test_rejects_redirect_uri_mismatch():
    with pytest.raises(HTTPException) as exc:
        _call(_make_row(), redirect_uri="https://evil/cb")
    assert "redirect_uri mismatch" in str(exc.value.detail)


def test_rejects_bad_pkce(monkeypatch):
    monkeypatch.setattr(grant, "verify_s256", lambda v, c: False)
    with pytest.raises(HTTPException) as exc:
        _call(_make_row())
    assert "PKCE" in str(exc.value.detail)


def test_rejects_row_without_identity_binding(monkeypatch):
    monkeypatch.setattr(grant, "verify_s256", lambda v, c: True)
    with pytest.raises(HTTPException) as exc:
        _call(_make_row(clerk_user_id=None))
    assert "identity binding" in str(exc.value.detail)


def test_rejects_missing_required_params():
    with pytest.raises(HTTPException):
        grant.handle(code="", code_verifier="v", client_id="c", redirect_uri="r", db=_StubDb(None))
    with pytest.raises(HTTPException):
        grant.handle(code="c", code_verifier="", client_id="c", redirect_uri="r", db=_StubDb(None))
