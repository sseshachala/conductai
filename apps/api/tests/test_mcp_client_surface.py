"""Client attribution survives HTTP handshakes without becoming authentication."""
from uuid import UUID

import pytest

from app.mcp import http
from app.mcp import surface_session
from app.core.config import settings
from tests.test_mcp_http_streamable import _make_client, _rpc


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr("app.core.auth.get_clerk_user_email", lambda _: None)

    def observe(body, ctx, registry):
        return {"jsonrpc": "2.0", "id": body["id"], "result": {
            "surface": ctx.surface, "workspace_id": ctx.workspace_id,
            "actor_id": ctx.clerk_user_id, "session_id": ctx.session_id}}

    monkeypatch.setattr(http, "dispatch", observe)
    return _make_client(monkeypatch)


def initialize(client, name, **headers):
    return client.post("/mcp", json=_rpc("initialize", params={
        "clientInfo": {"name": name, "version": "1"}}),
        headers={"Authorization": "Bearer fixture-token", **headers})


def invoke(client, session, **headers):
    return client.post("/mcp", json=_rpc("tools/call", params={
        "name": "guard_activity", "arguments": {"summary": "synthetic-canary"}}),
        headers={"Authorization": "Bearer fixture-token", "Mcp-Session-Id": session, **headers})


def test_chatgpt_initialize_and_call_do_not_inherit_codex_header(client):
    connected = initialize(client, "ChatGPT", **{"X-Claude-Surface": "codex"})
    assert connected.json()["result"]["surface"] == "chatgpt"
    session = connected.headers["Mcp-Session-Id"]
    result = invoke(client, session, **{"X-Claude-Surface": "codex", "User-Agent": "codex"})
    assert result.json()["result"]["surface"] == "chatgpt"
    assert result.headers["Mcp-Session-Id"] == session
    audit_session = result.json()["result"]["session_id"]
    assert audit_session == connected.json()["result"]["session_id"]
    assert str(UUID(audit_session)) == audit_session
    assert audit_session != session


@pytest.mark.parametrize("name,expected", [
    ("ChatGPT Work", "chatgpt-work"), ("codex", "codex"),
    ("Claude.ai", "claude.ai"), ("GitHub Copilot CLI", "copilot-cli"), ("vscode", "vscode"),
])
def test_initialized_surface_survives_generic_tool_call_user_agent(client, name, expected):
    connected = initialize(client, name)
    result = invoke(client, connected.headers["Mcp-Session-Id"], **{"User-Agent": "codex"})
    assert result.json()["result"]["surface"] == expected


def test_canonical_surface_header_overrides_shared_runtime_name(client):
    connected = initialize(client, "codex", **{"X-Conduct-Ai-Tool": "chatgpt", "X-Claude-Surface": "codex"})
    result = invoke(client, connected.headers["Mcp-Session-Id"], **{"User-Agent": "codex"})
    assert connected.json()["result"]["surface"] == "chatgpt"
    assert result.json()["result"]["surface"] == "chatgpt"


def test_forged_surface_session_is_not_trusted(client):
    connected = initialize(client, "codex")
    session = connected.headers["Mcp-Session-Id"].replace(":codex:", ":chatgpt:")
    assert session != connected.headers["Mcp-Session-Id"]
    result = invoke(client, session, **{"User-Agent": "codex"})
    assert result.json()["result"]["surface"] == "codex"


@pytest.mark.parametrize("resolved", [("another-workspace", "user_x"), ("ws-abc", "another-user")])
def test_session_surface_cannot_cross_authenticated_workspace_or_actor(client, monkeypatch, resolved):
    connected = initialize(client, "ChatGPT")
    monkeypatch.setattr(http, "_resolve_workspace", lambda *_: resolved)
    result = invoke(client, connected.headers["Mcp-Session-Id"], **{"User-Agent": "codex"})
    assert result.json()["result"]["surface"] == "codex"
    assert result.json()["result"]["workspace_id"] == resolved[0]
    assert result.json()["result"]["actor_id"] == resolved[1]


def test_user_session_surface_survives_access_token_rotation(client):
    connected = initialize(client, "ChatGPT")
    result = invoke(client, connected.headers["Mcp-Session-Id"], **{
        "Authorization": "Bearer rotated-fixture-token", "User-Agent": "codex"})
    assert result.json()["result"]["surface"] == "chatgpt"


def test_service_session_surface_is_bound_to_credential(client, monkeypatch):
    monkeypatch.setattr(http, "_resolve_workspace", lambda *_: ("ws-abc", None))
    connected = initialize(client, "ChatGPT")
    result = invoke(client, connected.headers["Mcp-Session-Id"], **{
        "Authorization": "Bearer another-service-credential", "User-Agent": "codex"})
    assert result.json()["result"]["surface"] == "codex"


@pytest.mark.parametrize("token", [None, "revoked-fixture-token"])
def test_surface_session_never_bypasses_authentication(client, monkeypatch, token):
    connected = initialize(client, "ChatGPT")
    monkeypatch.setattr(http, "_resolve_workspace", lambda *_: None)
    headers = {"Mcp-Session-Id": connected.headers["Mcp-Session-Id"]}
    if token:
        headers["Authorization"] = "Bearer " + token
    result = client.post("/mcp", json=_rpc("tools/call"), headers=headers)
    assert result.status_code == 401


def test_surface_session_is_stateless_across_workers(client, monkeypatch):
    connected = initialize(client, "ChatGPT")
    other_worker = _make_client(monkeypatch)
    result = invoke(other_worker, connected.headers["Mcp-Session-Id"], **{"User-Agent": "codex"})
    assert result.json()["result"]["surface"] == "chatgpt"


def test_surface_session_is_opaque_unique_and_contains_no_credentials_or_actor(client):
    first = initialize(client, "ChatGPT").headers["Mcp-Session-Id"]
    second = initialize(client, "ChatGPT").headers["Mcp-Session-Id"]
    assert first != second
    assert 32 <= len(first) <= 255
    assert all(0x21 <= ord(char) <= 0x7E for char in first)
    assert all(value not in first for value in ("fixture-token", "ws-abc", "user_x"))


def test_unknown_client_retains_existing_uuid_and_legacy_fallback(client):
    connected = initialize(client, "unrecognized-fixture")
    session = connected.headers["Mcp-Session-Id"]
    UUID(session)
    result = invoke(client, session, **{"X-Claude-Surface": "cursor"})
    assert result.json()["result"]["surface"] == "cursor"


def test_tool_arguments_cannot_relabel_initialized_client(client):
    connected = initialize(client, "codex")
    result = client.post("/mcp", json=_rpc("tools/call", params={
        "clientInfo": {"name": "ChatGPT"}, "name": "guard_activity",
        "arguments": {"summary": "synthetic-canary", "surface": "chatgpt"}}),
        headers={"Authorization": "Bearer fixture-token",
                 "Mcp-Session-Id": connected.headers["Mcp-Session-Id"], "User-Agent": "codex"})
    assert result.json()["result"]["surface"] == "codex"


def test_legacy_header_cannot_fake_a_signed_session(client):
    session = "mcp1:00000000-0000-4000-8000-000000000001:chatgpt:" + "0" * 64
    result = invoke(client, session, **{"User-Agent": "codex"})
    assert result.json()["result"]["surface"] == "codex"


def test_explicit_audit_session_preserves_existing_correlation(client):
    audit_session = str(UUID("11111111-2222-4333-8444-555555555555"))
    connected = initialize(client, "ChatGPT", **{"X-Session-Id": audit_session})
    result = invoke(client, connected.headers["Mcp-Session-Id"], **{"X-Session-Id": audit_session})
    assert result.json()["result"]["session_id"] == audit_session
    assert result.json()["result"]["surface"] == "chatgpt"


def test_signing_key_rotation_invalidates_only_surface_metadata(client, monkeypatch):
    connected = initialize(client, "ChatGPT")
    monkeypatch.setattr(settings, "encryption_key", "rotated-fixture-key-for-testing-only")
    result = invoke(client, connected.headers["Mcp-Session-Id"], **{"User-Agent": "codex"})
    assert result.status_code == 200
    assert result.json()["result"]["surface"] == "codex"


@pytest.mark.parametrize("session", [
    "", "mcp1:invalid:chatgpt:" + "a" * 64,
    "mcp1:00000000-0000-4000-8000-000000000001:chatgpt:" + "z" * 64,
    "mcp1:00000000-0000-4000-8000-000000000001:unrecognized:" + "a" * 64,
    "mcp1:00000000-0000-4000-8000-000000000001:chatgpt:" + "a" * 512,
])
def test_malformed_surface_metadata_is_ignored(session):
    assert surface_session.resolve(session, "ws-abc", "user_x", "fixture-token") is None
