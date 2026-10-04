"""Rate-limit picker labels are local, workspace scoped, and non-authoritative."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.config import settings
from app.modules.agent_identity.labels import agent_options as _profile_agent_options


def agent(identity_id, name):
    return SimpleNamespace(id=identity_id, name=name)


def test_named_agents_preserved_without_profile_lookup():
    db = MagicMock()
    rows = [agent("one", "Build agent"), agent("two", "alice@example.test (auto)")]
    assert _profile_agent_options(db, "workspace", rows) == [
        {"id": "one", "name": "Build agent"}, {"id": "two", "name": "alice@example.test (auto)"},
    ]
    db.query.assert_not_called()


def test_clerk_auto_agents_resolve_member_emails_in_one_local_query(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "clerk")
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(clerk_id="user_alice", email=" alice@example.test "),
    ]
    rows = [agent("one", "user_alice (auto)"), agent("two", "user_alice (auto)"),
            agent("three", "user_unknown (auto)")]
    assert _profile_agent_options(db, "workspace", rows) == [
        {"id": "one", "name": "alice@example.test (auto)"},
        {"id": "two", "name": "alice@example.test (auto)"},
        {"id": "three", "name": "Auto-provisioned agent"},
    ]
    db.query.assert_called_once()
    filters = db.query.return_value.join.return_value.filter.call_args.args
    assert filters[0].left.table.name == "workspace_users"
    assert filters[0].right.value == "workspace"
    assert filters[1].right.value == ["user_alice", "user_unknown"]
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_oidc_auto_agents_use_issuer_and_workspace_scoped_display_names(monkeypatch):
    monkeypatch.setattr(settings, "auth_mode", "proxy")
    monkeypatch.setattr(settings, "console_oidc_issuer", "https://issuer.example.test/realm")
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = [
        SimpleNamespace(user_id="oidc_alice", display_name=" Alice "),
        SimpleNamespace(user_id="oidc_blank", display_name=" "),
    ]
    rows = [agent("one", "oidc_alice (auto)"), agent("two", "oidc_blank (auto)")]
    assert _profile_agent_options(db, "workspace", rows) == [
        {"id": "one", "name": "Alice (auto)"}, {"id": "two", "name": "Auto-provisioned agent"},
    ]
    filters = db.query.return_value.join.return_value.filter.call_args.args
    assert filters[0].right.value == "workspace"
    assert filters[1].right.value == settings.console_oidc_issuer
    assert filters[2].right.value == ["oidc_alice", "oidc_blank"]
    db.query.assert_called_once()


@pytest.mark.parametrize("mode", ["clerk", "proxy"])
def test_missing_local_profiles_do_not_expose_raw_owner_ids(monkeypatch, mode):
    monkeypatch.setattr(settings, "auth_mode", mode)
    db = MagicMock()
    db.query.return_value.join.return_value.filter.return_value.all.return_value = []
    assert _profile_agent_options(db, "workspace", [agent("one", "user_missing (auto)")]) == [
        {"id": "one", "name": "Auto-provisioned agent"},
    ]


def test_profile_endpoint_rejects_agent_caps_without_changing_shared_cap(monkeypatch):
    from uuid import uuid4
    from app.routers import gateway_profiles_v2 as router

    workspace, profile, identity = str(uuid4()), uuid4(), str(uuid4())
    shared = SimpleNamespace(agent_identity_id=None, rpm=120, tpm=250000)
    override = SimpleNamespace(agent_identity_id=identity, rpm=5, tpm=1000)
    db, identity_query, cap_query = MagicMock(), MagicMock(), MagicMock()
    identity_query.filter.return_value.all.return_value = [agent(identity, "Worker")]
    cap_query.filter.return_value.all.return_value = [shared, override]
    db.query.side_effect = [identity_query, cap_query]
    monkeypatch.setattr(router, "_load_profile", MagicMock())
    monkeypatch.setattr(router, "_profile_rate_limits_output", MagicMock())
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as error:
        router.update_profile_rate_limits(workspace, profile, router.ProfileRateLimitsBody(agent_limits=[{
            "agent_identity_id": identity, "rpm": 10, "tpm": 2000,
        }]), db)
    assert error.value.status_code == 400
    assert (shared.rpm, shared.tpm) == (120, 250000)
    assert (override.rpm, override.tpm) == (5, 1000)
    db.delete.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_empty_legacy_agent_input_does_not_remove_any_caps(monkeypatch):
    from uuid import uuid4
    from app.routers import gateway_profiles_v2 as router

    shared = SimpleNamespace(agent_identity_id=None, rpm=60, tpm=100000)
    override = SimpleNamespace(agent_identity_id=str(uuid4()), rpm=2, tpm=500)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [shared, override]
    monkeypatch.setattr(router, "_load_profile", MagicMock())
    monkeypatch.setattr(router, "_profile_rate_limits_output", MagicMock())
    router.update_profile_rate_limits(str(uuid4()), uuid4(), router.ProfileRateLimitsBody(agent_limits=[]), db)
    assert (shared.rpm, shared.tpm) == (60, 100000)
    db.delete.assert_not_called()
    db.add.assert_not_called()


def test_agent_only_save_does_not_create_a_shared_cap(monkeypatch):
    from uuid import uuid4
    from app.routers import gateway_profiles_v2 as router

    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    monkeypatch.setattr(router, "_load_profile", MagicMock())
    monkeypatch.setattr(router, "_profile_rate_limits_output", MagicMock())
    router.update_profile_rate_limits(str(uuid4()), uuid4(), router.ProfileRateLimitsBody(agent_limits=[]), db)
    db.add.assert_not_called()
    db.delete.assert_not_called()
