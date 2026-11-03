import io
import json
import sys
from email.message import Message
from urllib.error import HTTPError

import pytest

from conduct_cli import revocation
from conduct_cli.commands import auth, shared
from conduct_cli.hooks import pretooluse

TOKEN = "cond_agt_s1_" + "a" * 40


def _error(code, state=None):
    headers = Message()
    if state:
        headers[revocation.IDENTITY_STATE_HEADER] = state
    return HTTPError("https://api.test/auth/refresh", code, "inactive", headers, io.BytesIO())


@pytest.fixture(autouse=True)
def marker(tmp_path, monkeypatch):
    path = tmp_path / "identity-revoked.json"
    monkeypatch.setattr(revocation, "MARKER_PATH", path)
    return path


@pytest.mark.parametrize("code,state,expected", [
    (401, "deactivated", True), (401, "Deactivated", True),
    (401, None, False), (401, "expired", False), (403, "deactivated", False),
])
def test_only_explicit_deactivation_counts(code, state, expected):
    assert revocation.is_deactivation(_error(code, state)) is expected


def test_marker_is_bound_to_the_rejected_token(marker):
    revocation.mark_revoked(TOKEN)
    assert revocation.is_revoked(TOKEN)
    assert not revocation.is_revoked("cond_agt_s1_" + "b" * 40)
    assert not marker.exists(), "a new token clears the marker"


def test_refresh_rejection_sets_marker(tmp_path, monkeypatch, marker):
    config = tmp_path / "config.json"
    cfg = {"api_url": "https://api.test", "workspace_id": "ws", "agent_token": TOKEN, "refresh_token": "cond_ref_s1_x"}
    config.write_text(json.dumps(cfg))
    monkeypatch.setattr(shared, "CONFIG_PATH", config)
    monkeypatch.setattr(auth, "CONFIG_PATH", config)

    def refuse(*_a, **_k):
        raise _error(401, "deactivated")

    monkeypatch.setattr(auth.urllib.request, "urlopen", refuse)
    assert auth._rotate_agent_token(cfg) is False
    assert revocation.is_revoked(TOKEN)


def test_expired_refresh_does_not_set_marker(tmp_path, monkeypatch, marker):
    cfg = {"api_url": "https://api.test", "agent_token": TOKEN, "refresh_token": "cond_ref_s1_x"}

    def refuse(*_a, **_k):
        raise _error(401)

    monkeypatch.setattr(auth.urllib.request, "urlopen", refuse)
    assert auth._rotate_agent_token(cfg) is False
    assert not marker.exists()


def _run_hook(monkeypatch, token):
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})))
    monkeypatch.setattr(pretooluse, "record_hook_heartbeat", lambda *_: None)
    monkeypatch.setattr(pretooluse, "_maybe_sync_policy", lambda: None)
    monkeypatch.setattr(pretooluse, "_should_periodic_flush", lambda: False)
    monkeypatch.setattr(pretooluse, "load_config", lambda: {"agent_token": token})
    monkeypatch.setattr("conduct_cli.hooks.session_usage.handle", lambda _d: None)
    with pytest.raises(SystemExit) as exit_info:
        pretooluse.main()
    return exit_info.value.code


def test_hook_blocks_every_tool_call_when_revoked(monkeypatch, capsys):
    revocation.mark_revoked(TOKEN)
    assert _run_hook(monkeypatch, TOKEN) == 2
    assert "deactivated by your workspace admin" in capsys.readouterr().err
