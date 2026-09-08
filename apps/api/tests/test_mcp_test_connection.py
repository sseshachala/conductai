"""Auth-resolution chain for POST /mcp-servers/test-connection.

The Test Connection button in /integrations must be usable after Save —
i.e. re-testing an existing server should use the SAVED token, not require
the user to re-paste. Regression coverage for the "re-test always 401s"
bug where the endpoint only trusted body.auth_token.

Resolution order:
  1. body.auth_token       — typed value wins (lets user validate NEW tokens)
  2. body.server_id        — falls back to saved (workspace-scoped decrypt)
  3. body.credential_key   — env-var fallback

Runs unit-mode (no DB, no network): patches list_tools and the DB session
lookup so the tests exercise the resolver, not the transport.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.crypto import encrypt as _encrypt
from app.main import app


def _stub_deps(monkeypatch, *, workspace_id="ws-1", saved_token=None, saved_ws="ws-1"):
    """Patch auth + DB dependencies so the endpoint runs without a real request.

    Returns a MagicMock for list_tools so the caller can assert what token
    the resolver produced.
    """
    from app.core import auth as _auth
    from app.core import database as _db

    app.dependency_overrides[_auth.get_workspace_id] = lambda: workspace_id
    app.dependency_overrides[_auth.require_permission("platform.credentials.manage")] = lambda: "test-user"

    fake_db = MagicMock()
    if saved_token is not None and saved_ws == workspace_id:
        fake_row = MagicMock()
        fake_row.encrypted_auth = _encrypt({"token": saved_token})
        fake_db.execute.return_value.fetchone.return_value = fake_row
    else:
        fake_db.execute.return_value.fetchone.return_value = None

    app.dependency_overrides[_db.get_db] = lambda: fake_db

    mock_list = MagicMock(return_value=([{"name": "tool_a"}], "http"))
    monkeypatch.setattr(
        "app.runtime.integrations.mcp_client.list_tools",
        mock_list,
    )
    return mock_list


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_typed_auth_token_wins_over_saved(monkeypatch):
    """Rule 1: if the form field has a value, use it — even if a saved token exists."""
    mock_list = _stub_deps(monkeypatch, saved_token="saved-token-xxx")

    r = TestClient(app).post(
        "/mcp-servers/test-connection",
        json={
            "url": "https://example.com/mcp",
            "auth_token": "typed-token-yyy",
            "server_id": "row-1",
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    # list_tools called with the TYPED token, not the saved one
    args, _ = mock_list.call_args
    assert args[1] == "typed-token-yyy"


def test_saved_token_used_when_field_empty(monkeypatch):
    """Rule 2 — the actual bug fix: empty field + server_id → decrypt saved."""
    mock_list = _stub_deps(monkeypatch, saved_token="saved-token-xxx")

    r = TestClient(app).post(
        "/mcp-servers/test-connection",
        json={
            "url": "https://example.com/mcp",
            "auth_token": None,
            "server_id": "row-1",
        },
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    args, _ = mock_list.call_args
    assert args[1] == "saved-token-xxx"


def test_saved_token_ignored_when_server_id_from_other_workspace(monkeypatch):
    """Never leak another workspace's token. Row lookup is scoped by workspace_id."""
    mock_list = _stub_deps(
        monkeypatch,
        workspace_id="ws-A",
        saved_token="ws-B-secret",
        saved_ws="ws-B",  # simulated: row belongs to a different workspace
    )

    r = TestClient(app).post(
        "/mcp-servers/test-connection",
        json={
            "url": "https://example.com/mcp",
            "auth_token": None,
            "server_id": "row-from-ws-B",
        },
    )
    assert r.status_code == 200
    # list_tools was called with None (row lookup returned no match under ws-A)
    args, _ = mock_list.call_args
    assert args[1] is None


def test_no_server_id_no_token_falls_through_to_credential_key(monkeypatch):
    """Rule 3: nothing typed, no server_id → try credential_key env-var fallback."""
    mock_list = _stub_deps(monkeypatch, saved_token=None)
    monkeypatch.setattr(
        "app.runtime.mcp_credentials.resolve_mcp_token_by_credential_key",
        lambda key, ws, env, db: "env-fallback-token",
    )

    r = TestClient(app).post(
        "/mcp-servers/test-connection",
        json={
            "url": "https://example.com/mcp",
            "auth_token": None,
            "credential_key": "GITHUB_TOKEN",
        },
    )
    assert r.status_code == 200
    args, _ = mock_list.call_args
    assert args[1] == "env-fallback-token"
