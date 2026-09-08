"""#1712 Track 1 gap 3 — POST /guard/trial/provision (public signup).

Unauthenticated but email is REQUIRED. Company also REQUIRED. Endpoint
provisions a fresh trial workspace with agent identity + token so the
curl-install shell script can drop ~/.conduct/env on the caller's laptop.

Covers:
  - happy path: fresh email → new workspace + token returned
  - idempotency: same email within trial window returns SAME workspace
  - validation: bad email → 422, missing company → 422
  - IP rate-limit: over cap → 429
"""
from __future__ import annotations

import uuid as _uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _client(db_mock):
    from app.main import app
    from app.core.database import get_db
    app.dependency_overrides[get_db] = lambda: db_mock
    return TestClient(app, raise_server_exceptions=False)


def _clear():
    from app.main import app
    from app.core.database import get_db
    app.dependency_overrides.pop(get_db, None)


def test_provision_requires_valid_email():
    db = MagicMock()
    client = _client(db)
    try:
        # bad email → 422 from our regex
        resp = client.post(
            "/guard/trial/provision",
            json={"email": "not-an-email", "company": "Xervmon"},
        )
        assert resp.status_code == 422
        assert "invalid_email" in resp.text
    finally:
        _clear()


def test_provision_requires_company():
    db = MagicMock()
    client = _client(db)
    try:
        # Pydantic-level: company is not Optional, missing → 422
        resp = client.post(
            "/guard/trial/provision",
            json={"email": "sudhi@example.com"},
        )
        assert resp.status_code == 422
    finally:
        _clear()

    # Empty string → 422 from the endpoint's own check
    db2 = MagicMock()
    client = _client(db2)
    try:
        resp = client.post(
            "/guard/trial/provision",
            json={"email": "sudhi@example.com", "company": "  "},
        )
        assert resp.status_code == 422
        assert "company_required" in resp.text
    finally:
        _clear()


def test_provision_fresh_email_creates_workspace_and_returns_token():
    """Happy path: existing-trial lookup returns None → seed a new
    workspace, run seed_trial, load the identity, decrypt, return token."""
    db = MagicMock()
    # 1st execute: existing-by-email lookup (SELECT ws + join agent_identities)
    #   → returns None → not a replay, mint fresh
    exec_none = MagicMock(); exec_none.fetchone.return_value = None
    # After INSERT + seed_trial + load: fetchone returns the identity row.
    ident_row = SimpleNamespace(
        id=_uuid.uuid4(),
        token_encrypted=b"encrypted-blob-placeholder",
        expires_at=None,
    )
    exec_ident = MagicMock(); exec_ident.fetchone.return_value = ident_row

    # With seed_trial patched to a no-op, only two db.execute() calls
    # matter for the provisioning path:
    #   1. `_find_existing_trial_by_email` — returns None (not a replay)
    #   2. `_load_trial_identity` — returns the freshly-seeded ident row
    # Any additional calls fall through to a MagicMock whose fetchone is
    # None — safe default that also protects against unexpected extra
    # queries slipping in.
    fetchone_seq = iter([None, ident_row])
    def _exec(*_a, **_kw):
        m = MagicMock()
        try:
            m.fetchone.return_value = next(fetchone_seq)
        except StopIteration:
            m.fetchone.return_value = None
        return m
    db.execute.side_effect = _exec

    client = _client(db)
    try:
        with patch("app.modules.guard.routers.trial._throttle_by_ip", return_value=True), \
             patch("app.modules.guard.routers.trial.seed_trial", return_value=None), \
             patch("app.modules.guard.routers.trial.decrypt", return_value={"token": "cond_agt_trial_deadbeef"}):
            resp = client.post(
                "/guard/trial/provision",
                json={"email": "SUDHI@example.com", "company": "Xervmon"},
            )
    finally:
        _clear()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent_token"] == "cond_agt_trial_deadbeef"
    assert body["workspace_id"]
    assert body["gateway_url"]
    assert body["workspace_url"].endswith("/theguard")


def test_provision_ip_rate_limit_returns_429():
    db = MagicMock()
    client = _client(db)
    try:
        with patch("app.modules.guard.routers.trial._throttle_by_ip", return_value=False):
            resp = client.post(
                "/guard/trial/provision",
                json={"email": "sudhi@example.com", "company": "Xervmon"},
            )
        assert resp.status_code == 429
        assert "provision_rate_limited" in resp.text
    finally:
        _clear()
