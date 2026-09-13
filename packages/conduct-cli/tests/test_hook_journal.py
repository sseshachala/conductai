from __future__ import annotations

import json
import os
from urllib.error import HTTPError

from conduct_cli.hooks import base


def _redirect_journal(tmp_path, monkeypatch):
    journal = tmp_path / "journal"
    monkeypatch.setattr(base, "JOURNAL_DIR", journal)
    monkeypatch.setattr(base, "JOURNAL_DEAD_DIR", journal / "dead-letter")
    monkeypatch.setattr(base, "JOURNAL_PID_PATH", journal / "drain.pid")
    monkeypatch.setattr(base.time, "sleep", lambda _seconds: None)
    return journal


def test_permanent_delivery_failure_moves_event_to_dead_letter(tmp_path, monkeypatch):
    journal = _redirect_journal(tmp_path, monkeypatch)
    base.journal_append(json.dumps({"workspace_id": "workspace"}), "https://api.test")

    def _fail(*args, **kwargs):
        raise HTTPError("https://api.test", 400, "bad request", {}, None)

    monkeypatch.setattr(base.urllib.request, "urlopen", _fail)
    base.run_drain_daemon()

    assert not list(journal.glob("*.json"))
    dead = list((journal / "dead-letter").glob("*.json"))
    assert len(dead) == 1
    if os.name != "nt":
        assert dead[0].stat().st_mode & 0o077 == 0
    entry = json.loads(dead[0].read_text())
    assert entry["attempts"] == 1
    assert entry["last_error"] == "HTTP 400"


def test_successful_delivery_removes_event(tmp_path, monkeypatch):
    journal = _redirect_journal(tmp_path, monkeypatch)
    base.journal_append(json.dumps({"workspace_id": "workspace"}), "https://api.test")

    class _Ok:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(base.urllib.request, "urlopen", lambda *args, **kwargs: _Ok())
    base.run_drain_daemon()
    assert not list(journal.glob("*.json"))


def test_hook_heartbeat_contains_no_request_data(tmp_path, monkeypatch):
    heartbeat = tmp_path / "heartbeat.json"
    monkeypatch.setattr(base, "HOOK_HEARTBEAT_PATH", heartbeat)
    monkeypatch.setattr(base, "GUARD_DIR", tmp_path)
    base.record_hook_heartbeat("post_tool_use")
    data = json.loads(heartbeat.read_text())
    assert data["event"] == "post_tool_use"
    assert set(data) == {"event", "ts"}
    if os.name != "nt":
        assert heartbeat.stat().st_mode & 0o077 == 0
