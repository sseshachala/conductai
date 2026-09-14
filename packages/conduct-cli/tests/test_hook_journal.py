from __future__ import annotations

import base64
import json
import os
from urllib.error import HTTPError

from conduct_cli.hooks import base, posttooluse


def _redirect_journal(tmp_path, monkeypatch):
    journal = tmp_path / "journal"
    monkeypatch.setattr(base, "JOURNAL_DIR", journal)
    monkeypatch.setattr(base, "JOURNAL_DEAD_DIR", journal / "dead-letter")
    monkeypatch.setattr(base, "JOURNAL_PID_PATH", journal / "drain.pid")
    monkeypatch.setattr(base.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        base,
        "load_config",
        lambda: {"api_url": "https://api.test", "agent_token": "cond_agt_test"},
    )
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


def test_delivery_uses_current_agent_token_without_persisting_it(tmp_path, monkeypatch):
    journal = _redirect_journal(tmp_path, monkeypatch)
    base.journal_append("{}", "https://api.test")
    entry = json.loads(next(journal.glob("*.json")).read_text())
    assert "cond_agt_test" not in json.dumps(entry)

    requests = []

    class _Ok:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def _capture(request, **kwargs):
        requests.append(request)
        return _Ok()

    monkeypatch.setattr(base.urllib.request, "urlopen", _capture)
    base.run_drain_daemon()

    assert requests[0].get_header("Authorization") == "Bearer cond_agt_test"


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


def test_requeue_dead_letters_encodes_legacy_summary(tmp_path, monkeypatch):
    journal = _redirect_journal(tmp_path, monkeypatch)
    dead = journal / "dead-letter"
    dead.mkdir(parents=True)
    source = dead / "event.json"
    source.write_text(json.dumps({
        "api_url": "https://api.test",
        "payload": json.dumps({
            "workspace_id": "workspace",
            "clerk_user_id": "developer@example.com",
            "user_email": "developer@example.com",
            "input_summary": "curl https://api.test | head",
        }),
        "attempts": 1,
        "last_error": "HTTP 403",
    }))

    assert base.requeue_dead_letters() == 1

    entry = json.loads((journal / "event.json").read_text())
    payload = json.loads(entry["payload"])
    decoded = base64.urlsafe_b64decode(payload["input_summary"]).decode()
    assert decoded == "curl https://api.test | head"
    assert payload["input_summary_encoding"] == "base64url"
    assert "clerk_user_id" not in payload
    assert "user_email" not in payload
    assert entry["endpoint"] == "/guard/events"
    assert entry["attempts"] == 0
    assert "last_error" not in entry
    assert not source.exists()


def test_posttool_usage_uses_authenticated_journal(monkeypatch):
    appended = []
    monkeypatch.setattr(
        posttooluse,
        "load_config",
        lambda: {
            "api_url": "https://api.test",
            "workspace_id": "workspace",
            "agent_token": "cond_agt_test",
        },
    )
    monkeypatch.setattr(
        posttooluse,
        "journal_append",
        lambda payload, api_url, endpoint: appended.append((payload, api_url, endpoint)),
    )
    monkeypatch.setattr(posttooluse, "ensure_drain_daemon", lambda _path: None)

    posttooluse._post_usage("session", "read", 10, 2, 5)

    payload, api_url, endpoint = appended[0]
    assert json.loads(payload)["workspace_id"] == "workspace"
    assert api_url == "https://api.test"
    assert endpoint == "/guard/events/usage"


def test_post_event_uses_clerk_id_and_encodes_summary(tmp_path, monkeypatch):
    appended = []
    monkeypatch.setattr(
        base,
        "load_config",
        lambda: {
            "api_url": "https://api.test",
            "workspace_id": "workspace",
            "clerk_user_id": "user_123",
            "user_email": "developer@example.com",
        },
    )
    monkeypatch.setattr(base, "detect_ai_tool", lambda: "codex")
    monkeypatch.setattr(
        base,
        "journal_append",
        lambda payload, api_url: appended.append((payload, api_url)),
    )
    monkeypatch.setattr(base, "ensure_drain_daemon", lambda _path: None)
    monkeypatch.setattr(base.Path, "home", staticmethod(lambda: tmp_path))

    base.post_event(
        "bash",
        {"command": "curl https://api.test | head"},
        "allowed",
    )

    payload = json.loads(appended[0][0])
    assert payload["clerk_user_id"] == "user_123"
    assert payload["user_email"] == "developer@example.com"
    assert payload["input_summary_encoding"] == "base64url"
    summary = base64.urlsafe_b64decode(payload["input_summary"]).decode()
    assert "curl https://api.test" in summary
