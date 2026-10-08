"""The canonical MCP actor is server-authenticated, not an email or tool argument."""
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.mcp.server import _detect_surface
from app.modules.guard.routers import mcp_helpers as mcp
from app.tools.registrations import guard


def test_canonical_mcp_records_actor_and_agent_separately_from_email(monkeypatch):
    db = MagicMock()
    db.info = {"mcp_actor": {"clerk_user_id": "idp-test-subject", "agent_identity_id": str(uuid4())}}
    monkeypatch.setattr(mcp, "chain_hash_for_insert", lambda *args: (None, "test-entry-hash"))
    monkeypatch.setattr(mcp, "get_policy_hash", lambda *args: "test-policy-hash")
    mcp._record_event(db, uuid4(), "guard_activity", {"summary": "canary"}, "allowed", None,
                      "mcp-test", "synthetic@example.test", "fixture-session")
    event = db.add.call_args.args[0]
    assert event.clerk_user_id == "idp-test-subject"
    assert event.agent_identity_id == db.info["mcp_actor"]["agent_identity_id"]
    assert event.user_email == "synthetic@example.test"


def test_registration_passes_only_authenticated_context_to_audit(monkeypatch):
    db = MagicMock()
    db.info = {}
    monkeypatch.setattr("app.core.database.SessionLocal", lambda: db)
    monkeypatch.setattr("app.core.auth.resolve_agent_identity_row", lambda token, session: SimpleNamespace(id="test-agent"))
    ctx = SimpleNamespace(workspace_id=str(uuid4()), clerk_user_id="verified-subject", resolved_token="fixture-token",
                          user_email="synthetic@example.test", surface="http", session_id="fixture", identity=None)

    def impl(gctx, **kwargs):
        assert db.info["mcp_actor"] == {"clerk_user_id": "verified-subject", "agent_identity_id": "test-agent"}
        return "ok"

    assert guard._wrap(impl)(ctx=ctx, clerk_user_id="forged-subject") == "ok"
    db.close.assert_called_once()


@pytest.mark.parametrize("name", ["GitHub Copilot CLI", "copilot-cli", "copilot_cli"])
def test_copilot_cli_is_not_reported_as_vscode(name):
    assert _detect_surface({"name": name}) == "copilot-cli"
    assert _detect_surface({"name": "vscode"}) == "vscode"


@pytest.mark.parametrize("name", ["ChatGPT", "chatgpt.com", "OpenAI ChatGPT", "ChatGPT (Codex runtime)"])
def test_chatgpt_is_not_reported_as_codex(name):
    assert _detect_surface({"name": name}) == "chatgpt"


@pytest.mark.parametrize("name", ["ChatGPT Work", "chatgpt-work", "ChatGPT Work Desktop (Codex runtime)"])
def test_chatgpt_work_is_a_distinct_surface(name):
    assert _detect_surface({"name": name}) == "chatgpt-work"


@pytest.mark.parametrize("name", ["codex", "Codex CLI", "Codex Desktop", "codex_mcp_client"])
def test_actual_codex_clients_remain_codex(name):
    assert _detect_surface({"name": name}) == "codex"
