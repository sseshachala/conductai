from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.modules.guard.routers import trial
from app.modules.guard.trial_seed import link_trial_owner


@pytest.mark.parametrize("verb,status", [("allow", 200), ("warn", 200), ("block", 451), ("prove", 200)])
def test_demo_routes_to_correct_service(monkeypatch, verb, status):
    monkeypatch.setattr(trial.settings, "conduct_proxy_url", "https://gateway.example/gateway/v1")
    monkeypatch.setattr(trial.settings, "api_base_url", "https://api.example/")
    monkeypatch.setattr(trial, "_load_trial_identity", lambda *args: SimpleNamespace(token_encrypted="fixture"))
    monkeypatch.setattr(trial, "decrypt", lambda value: {"token": "test-only-token"})
    monkeypatch.setattr(trial, "_resolve_demo_model", lambda *args: "claude-test")
    client = MagicMock()
    response = MagicMock(status_code=status, text='{"valid":true}')
    response.json.return_value = {"valid": True}
    client.get.return_value = response
    client.post.return_value = response
    factory = MagicMock()
    factory.return_value.__enter__.return_value = client
    monkeypatch.setattr("httpx.Client", factory)
    result = trial.run_demo_verb(verb, workspace_id="workspace", _perm="view", db=MagicMock())
    assert result.upstream_status == status
    if verb == "prove":
        assert client.get.call_args.args[0] == "https://api.example/guard/events/audit/verify"
        client.post.assert_not_called()
    else:
        assert client.post.call_args.args[0] == "https://gateway.example/gateway/v1/anthropic/v1/messages"
        assert client.post.call_args.kwargs["headers"]["X-Conductai-Internal"] == "test-only-token"


def test_existing_trial_session_repairs_missing_link(monkeypatch):
    identity = SimpleNamespace(id="identity", expires_at=datetime.now(timezone.utc) + timedelta(days=2), token_encrypted="fixture")
    monkeypatch.setattr(trial, "_load_trial_identity", lambda *args: identity)
    monkeypatch.setattr(trial, "decrypt", lambda value: {"token": "test-only-token"})
    monkeypatch.setattr(trial, "get_trial_cap_used", lambda *args: 0)
    repair = MagicMock()
    monkeypatch.setattr("app.modules.guard.trial_seed.link_trial_owner", repair)
    db = MagicMock()
    db.execute.return_value.fetchone.return_value = SimpleNamespace(plan="free_trial")
    result = trial.get_trial_session(workspace_id="workspace", _perm="view", db=db)
    repair.assert_called_once_with(db, "workspace", "identity")
    db.commit.assert_called_once()
    assert result.token == "test-only-token"


def test_link_repair_requires_live_owner_membership_and_empty_slot():
    db = MagicMock()
    link_trial_owner(db, "workspace", "identity")
    sql = str(db.execute.call_args.args[0])
    for predicate in (
        "member.active = true", "member.agent_identity_id IS NULL",
        "member.clerk_user_id = workspace.owner_id",
        "membership.clerk_user_id = member.clerk_user_id",
        "identity.workspace_id = workspace.id", "identity.source = 'conduct_trial'",
        "identity.lifecycle_state = 'active'", "identity.expires_at > now()",
    ):
        assert predicate in sql


@pytest.mark.parametrize("scenario,expected", [
    ("new", "trial"), ("revoked", None), ("removed", None),
    ("already_linked", "other"), ("expired", None), ("cross_workspace", None),
])
def test_link_repair_updates_only_eligible_rows(scenario, expected):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    engine = create_engine("sqlite://")
    with engine.connect() as conn:
        conn.connection.driver_connection.create_function("now", 0, lambda: "2026-01-01")
        for sql in (
            "CREATE TABLE workspaces (id TEXT, owner_id TEXT)",
            "CREATE TABLE workspace_users (workspace_id TEXT, clerk_user_id TEXT)",
            "CREATE TABLE guard_member_config (workspace_id TEXT, clerk_user_id TEXT, active BOOLEAN, agent_identity_id TEXT)",
            "CREATE TABLE agent_identities (id TEXT, workspace_id TEXT, source TEXT, lifecycle_state TEXT, expires_at TEXT)",
            "INSERT INTO workspaces VALUES ('ws', 'owner')",
            "INSERT INTO workspace_users VALUES ('ws', 'owner')",
            "INSERT INTO guard_member_config VALUES ('ws', 'owner', true, NULL)",
            "INSERT INTO agent_identities VALUES ('trial', 'ws', 'conduct_trial', 'active', '2027-01-01')",
        ):
            conn.execute(text(sql))
        changes = {
            "revoked": "UPDATE guard_member_config SET active = false",
            "removed": "DELETE FROM workspace_users",
            "already_linked": "UPDATE guard_member_config SET agent_identity_id = 'other'",
            "expired": "UPDATE agent_identities SET expires_at = '2025-01-01'",
            "cross_workspace": "UPDATE agent_identities SET workspace_id = 'elsewhere'",
        }
        if scenario in changes:
            conn.execute(text(changes[scenario]))
        with Session(bind=conn) as db:
            link_trial_owner(db, "ws", "trial")
            link_trial_owner(db, "ws", "trial")
            assert db.execute(text("SELECT agent_identity_id FROM guard_member_config")).scalar() == expected
    engine.dispose()
