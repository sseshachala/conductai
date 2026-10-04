from unittest.mock import MagicMock

import pytest

from conduct_cli import identity


@pytest.fixture
def cfg():
    return {"api_url": "https://console-api.example.test/", "workspace_id": "workspace-a", "agent_token": "fixture-token"}


def test_current_credential_is_resolved_on_the_selected_deployment(monkeypatch, cfg):
    request = MagicMock(return_value={"workspace_id": "workspace-a", "identity": {"id": "agent-a", "name": "Alice"}})
    monkeypatch.setattr(identity.api, "req", request)
    assert identity.identity_label(cfg) == "Alice (agent-a)"
    request.assert_called_once_with("GET", "https://console-api.example.test/auth/whoami",
                                   identity.api.headers("workspace-a", "fixture-token"), timeout=5)


def test_switching_workspace_or_refreshing_token_never_uses_cached_identity(monkeypatch, cfg):
    request = MagicMock(side_effect=[
        {"workspace_id": "workspace-a", "identity": {"id": "agent-a", "name": "Alice"}},
        {"workspace_id": "workspace-b", "identity": {"id": "agent-b", "name": "Bob"}},
    ])
    monkeypatch.setattr(identity.api, "req", request)
    assert identity.current_identity(cfg)["id"] == "agent-a"
    cfg.update(workspace_id="workspace-b", agent_token="refreshed-fixture")
    assert identity.current_identity(cfg)["id"] == "agent-b"
    assert request.call_args.args[2] == identity.api.headers("workspace-b", "refreshed-fixture")


@pytest.mark.parametrize("response", [
    None, [], {"workspace_id": "other", "identity": {"id": "agent-b"}},
    {"workspace_id": "workspace-a", "identity": None},
    {"workspace_id": "workspace-a", "identity": {"id": ""}},
    {"workspace_id": "workspace-a", "identity": {"id": 123}},
])
def test_unresolved_or_wrong_workspace_identity_is_not_shown(monkeypatch, cfg, response):
    monkeypatch.setattr(identity.api, "req", lambda *a, **kw: response)
    assert identity.identity_label(cfg) == "unavailable"


@pytest.mark.parametrize("error", [RuntimeError("offline"), SystemExit(1)])
def test_offline_identity_does_not_break_status(monkeypatch, cfg, error):
    monkeypatch.setattr(identity.api, "req", MagicMock(side_effect=error))
    assert identity.identity_label(cfg) == "unavailable"


def test_missing_credential_never_queries_saas(monkeypatch):
    request = MagicMock()
    monkeypatch.setattr(identity.api, "req", request)
    assert identity.current_identity({}) is None
    request.assert_not_called()
