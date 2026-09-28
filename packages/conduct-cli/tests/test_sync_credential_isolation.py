"""A metadata fetch must never swap out a client's access/refresh pair."""

from conduct_cli.guard_commands import policy as _guard_policy
from conduct_cli.guard_commands import setup as _guard_setup
from conduct_cli.guard_commands import shared as _guard_shared
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from conduct_cli import guard


def test_sync_preserves_credentials_when_install_status_returns_another_token(monkeypatch):
    cfg = {
        "agent_token": "cond_agt_current-session",
        "refresh_token": "cond_ref_current-session",
        "workspace_id": "11111111-1111-4111-8111-111111111111",
        "token_expires_at": "2099-01-01T00:00:00+00:00",
    }
    original = cfg.copy()
    monkeypatch.setattr(_guard_setup, "_proactive_token_refresh", lambda: None)
    monkeypatch.setattr(_guard_shared, "_require_guard_config", lambda: cfg)
    monkeypatch.setattr(_guard_shared, "_api_url", lambda _: "https://api.example.test")
    monkeypatch.setattr(_guard_setup, "_check_and_upgrade_packages", lambda: None)
    monkeypatch.setattr(_guard_policy, "_save_policy", lambda _: None)
    request = Mock(side_effect=[{"rules": []}, {
        "agent_token": "cond_agt_another-client",
        "user_email": "synthetic@example.test",
        "clerk_user_id": "synthetic",
    }])
    monkeypatch.setattr(_guard_shared, "_req", request)

    class MetadataSaved(BaseException):
        pass

    def save(value):
        for key, expected in original.items():
            assert value[key] == expected
        assert value["clerk_user_id"] == "synthetic"
        raise MetadataSaved()

    monkeypatch.setattr(_guard_shared, "_save_guard_config", save)
    # Stop before machine configuration, process launches or external requests.
    with pytest.raises(MetadataSaved):
        guard.cmd_guard_sync(SimpleNamespace(dry_run=False))
    assert request.call_count == 2
    assert all(call.kwargs["token"] == original["agent_token"] for call in request.call_args_list)
