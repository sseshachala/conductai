"""Tests for local health details reported by ``conduct guard status``."""

import json
from unittest.mock import patch

import conduct_cli.guard as guard


def test_status_reports_recent_hook_heartbeat(tmp_path, capsys, monkeypatch):
    conduct_home = tmp_path / ".conduct"
    conduct_home.mkdir()
    (conduct_home / "hook-heartbeat.json").write_text(
        json.dumps({"event": "post_tool_use", "ts": 1_000.0})
    )

    monkeypatch.setattr(guard.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(guard.time, "time", lambda: 1_007.9)
    monkeypatch.setattr(guard, "_load_policy", lambda: {"rules": []})
    monkeypatch.setattr(
        guard,
        "_require_guard_config",
        lambda: {
            "workspace_id": "workspace-test",
            "user_email": "developer@example.com",
            "clerk_user_id": "user-test",
            "agent_token": "token-test",
            "api_url": "https://api.example.test",
        },
    )

    with patch.object(guard, "_req", side_effect=[{}, []]), patch(
        "conduct_cli.hooks.base.drain_daemon_status", return_value=("running", 123)
    ):
        guard.cmd_guard_status(None)

    output = capsys.readouterr().out
    assert "Hook heartbeat: post_tool_use" in output
    assert "7s ago" in output
