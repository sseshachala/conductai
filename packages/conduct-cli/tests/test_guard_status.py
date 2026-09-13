"""Tests for local health details reported by ``conduct guard status``."""

import json
from types import SimpleNamespace
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


def test_replay_events_requeues_and_starts_drain(tmp_path, capsys, monkeypatch):
    from conduct_cli.hooks import base

    dead = tmp_path / "dead-letter"
    dead.mkdir()
    (dead / "event.json").write_text("{}")
    monkeypatch.setattr(base, "JOURNAL_DEAD_DIR", dead)
    monkeypatch.setattr(guard, "_require_guard_config", lambda: {"agent_token": "cond_agt_test"})

    with patch.object(base, "requeue_dead_letters", return_value=1) as requeue, patch.object(
        base, "ensure_drain_daemon"
    ) as ensure:
        guard.cmd_guard_replay_events(SimpleNamespace(limit=None, dry_run=False))

    requeue.assert_called_once_with(limit=None)
    ensure.assert_called_once()
    assert "Requeued 1 dead-letter event" in capsys.readouterr().out
