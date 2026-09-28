import json
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest

from conduct_cli.hooks import copilot_usage as usage


@pytest.fixture
def collector(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "copilot"))
    cfg = {"workspace_id": "workspace", "clerk_user_id": "actor", "api_url": "https://api.example"}
    monkeypatch.setattr(usage.base, "load_config", lambda: cfg)
    journal = Mock(return_value=True)
    monkeypatch.setattr(usage.base, "journal_append", journal)
    monkeypatch.setattr(usage.base, "ensure_drain_daemon", Mock())
    session = str(uuid4())
    path = tmp_path / "copilot" / "session-state" / session / "events.jsonl"
    path.parent.mkdir(parents=True)
    return session, path, cfg, journal


def write_snapshot(path, count, event_id=None):
    record = {"id": event_id or str(uuid4()), "type": "session.shutdown",
              "timestamp": "2026-09-28T12:00:00Z", "data": {
                  "tokenDetails": {key: {"tokenCount": count} for key in usage.FIELDS},
                  "currentTokens": 999999, "totalPremiumRequests": 100,
                  "prompt": "never upload this"}}
    with path.open("a") as stream:
        stream.write(json.dumps(record) + "\n")
    return record


def collect(fixture):
    session, _, cfg, _ = fixture
    return usage.collect(session, Path("hook.py"), usage.context(cfg))


def test_session_deltas_include_cache_once_and_deduplicate(collector):
    _, path, _, journal = collector
    assert not collect(collector)
    write_snapshot(path, 10)
    assert collect(collector)
    first = json.loads(journal.call_args.args[0])
    assert first["input_tokens"] == 30
    assert first["output_tokens"] == 10
    assert "never upload" not in journal.call_args.args[0]
    assert not collect(collector)
    write_snapshot(path, 15)
    assert collect(collector)
    second = json.loads(journal.call_args.args[0])
    assert second["input_tokens"] == 15
    assert second["output_tokens"] == 5
    assert journal.call_count == 2


def test_initial_collection_does_not_backfill_history(collector):
    _, path, _, journal = collector
    write_snapshot(path, 10)
    assert not collect(collector)
    assert not journal.called


def test_journal_failure_does_not_advance_cursor(collector):
    _, path, _, journal = collector
    collect(collector)
    write_snapshot(path, 10)
    journal.return_value = False
    assert not collect(collector)
    first = journal.call_args.args[0]
    journal.return_value = True
    assert collect(collector)
    assert journal.call_args.args[0] == first


def test_counter_reset_stays_unavailable(collector):
    _, path, _, journal = collector
    write_snapshot(path, 10)
    collect(collector)
    write_snapshot(path, 1)
    assert not collect(collector)
    journal.assert_not_called()


def test_workspace_change_does_not_upload(collector):
    session, path, cfg, journal = collector
    collect(collector)
    write_snapshot(path, 10)
    expected = usage.context(cfg)
    cfg["workspace_id"] = "other"
    assert not usage.collect(session, Path("hook.py"), expected)
    journal.assert_not_called()


@pytest.mark.parametrize("session", ["../../config", "", "not-a-uuid"])
def test_reject_session_paths(collector, session):
    with pytest.raises(ValueError):
        usage.collect(session, Path("hook.py"), usage.context(collector[2]))


@pytest.mark.parametrize("count", [-1, True, 1.5, None, 2**31])
def test_invalid_counters_not_guessed(collector, count):
    _, path, _, journal = collector
    collect(collector)
    write_snapshot(path, count)
    with pytest.raises(ValueError):
        collect(collector)
    journal.assert_not_called()


def test_session_end_worker_is_detached_and_has_no_credentials(collector, monkeypatch):
    session, _, cfg, _ = collector
    cfg["agent_token"] = "secret"
    spawn = Mock()
    monkeypatch.setattr(usage.subprocess, "Popen", spawn)
    usage.handle("session-end", {"sessionId": session}, Path("hook.py"))
    assert "secret" not in str(spawn.call_args)
    assert spawn.call_args.kwargs.get("start_new_session") or spawn.call_args.kwargs.get("creationflags")
