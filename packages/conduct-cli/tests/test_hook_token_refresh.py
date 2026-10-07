import io
import json
from datetime import datetime, timezone
from urllib.error import HTTPError

import pytest

from conduct_cli.commands import auth, shared
from conduct_cli.hooks import base
from conduct_cli.credential_lock import credential_lock


@pytest.fixture
def environment(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"api_url": "https://api.test", "workspace_id": "ws",
                                 "agent_token": "old", "refresh_token": "refresh-old"}))
    monkeypatch.setattr(shared, "CONFIG_PATH", config)
    monkeypatch.setattr(auth, "CONFIG_PATH", config)
    monkeypatch.setattr(base, "CONFIG_PATH", config)
    journal = tmp_path / "journal"
    monkeypatch.setattr(base, "JOURNAL_DIR", journal)
    monkeypatch.setattr(base, "JOURNAL_DEAD_DIR", journal / "dead-letter")
    monkeypatch.setattr(base, "JOURNAL_PID_PATH", journal / "drain.pid")
    monkeypatch.setattr(base.time, "sleep", lambda _: None)
    monkeypatch.setattr(base, "_refresh_policy_from_api", lambda: None)
    return config, journal


def refresh_response():
    return io.BytesIO(json.dumps({"agent_token": "new", "refresh_token": "refresh-new",
                                 "workspace_id": "ws", "expires_in": 600}).encode())


@pytest.mark.parametrize("surface", ["claude-code", "codex-desktop"])
@pytest.mark.parametrize("endpoint", ["/guard/events", "/guard/events/usage"])
def test_refresh_and_retry_preserves_payload(environment, monkeypatch, surface, endpoint):
    config, journal = environment
    payload = json.dumps({"workspace_id": "ws", "ai_tool": surface, "session_id": "session"})
    base.journal_append(payload, "https://api.test", endpoint=endpoint)
    calls = []

    def request(req, **_):
        calls.append((req.full_url, req.get_header("Authorization"), req.data))
        if req.full_url.endswith("/auth/refresh"):
            assert json.loads(req.data) == {"refresh_token": "refresh-old"}
            return refresh_response()
        if req.get_header("Authorization") == "Bearer old":
            raise HTTPError(req.full_url, 401, "expired", {}, io.BytesIO())
        return io.BytesIO(b"{}")

    monkeypatch.setattr(base.urllib.request, "urlopen", request)
    base.run_drain_daemon()
    assert len(calls) == 3
    assert calls[0][2] == calls[2][2] == payload.encode()
    assert calls[2][1] == "Bearer new"
    assert not list(journal.glob("*.json"))
    saved = json.loads(config.read_text())
    assert saved["refresh_token"] == "refresh-new"
    remaining = (datetime.fromisoformat(saved["token_expires_at"]) - datetime.now(timezone.utc)).total_seconds()
    assert 590 < remaining <= 600


@pytest.mark.parametrize("refresh_status", [401, 503])
def test_refresh_failure_retains_queue_and_backs_off(environment, monkeypatch, refresh_status):
    config, journal = environment
    for _ in range(3):
        base.journal_append("{}", "https://api.test")
    calls = []

    def request(req, **_):
        calls.append(req.full_url)
        status = refresh_status if req.full_url.endswith("/auth/refresh") else 401
        raise HTTPError(req.full_url, status, "failure", {}, io.BytesIO())

    monkeypatch.setattr(base.urllib.request, "urlopen", request)
    base.run_drain_daemon()
    base.run_drain_daemon()
    assert len(calls) == 2
    assert len(list(journal.glob("*.json"))) == 3
    assert not list((journal / "dead-letter").glob("*.json"))
    assert json.loads(config.read_text())["agent_token"] == "old"
    assert "refresh-old" not in (journal / "auth-retry").read_text()
    updated = json.loads(config.read_text())
    updated["agent_token"] = "new-login"
    config.write_text(json.dumps(updated))
    monkeypatch.setattr(base.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(b"{}"))
    base.run_drain_daemon()
    assert not list(journal.glob("*.json"))


def test_retry_401_does_not_loop(environment, monkeypatch):
    _, journal = environment
    base.journal_append("{}", "https://api.test")
    calls = []

    def request(req, **_):
        calls.append(req.full_url)
        if req.full_url.endswith("/auth/refresh"):
            return refresh_response()
        raise HTTPError(req.full_url, 401, "revoked", {}, io.BytesIO())

    monkeypatch.setattr(base.urllib.request, "urlopen", request)
    base.run_drain_daemon()
    assert len(calls) == 3
    assert len(list(journal.glob("*.json"))) == 1


def test_other_process_rotation_is_reused(environment, monkeypatch):
    config, _ = environment
    snapshot = json.loads(config.read_text())
    updated = dict(snapshot, agent_token="other-process-token", refresh_token="other-refresh")
    config.write_text(json.dumps(updated))
    monkeypatch.setattr(auth.urllib.request, "urlopen", lambda *a, **k: pytest.fail("extra rotation"))
    assert auth._refresh_agent_token(expected_config=snapshot)


def test_workspace_switch_is_not_overwritten(environment, monkeypatch):
    config, _ = environment

    def request(*a, **k):
        config.write_text(json.dumps({"workspace_id": "different", "agent_token": "other"}))
        return refresh_response()

    monkeypatch.setattr(auth.urllib.request, "urlopen", request)
    assert not auth._refresh_agent_token()
    assert json.loads(config.read_text())["workspace_id"] == "different"


def test_lock_prevents_concurrent_rotation(environment):
    config, _ = environment
    with credential_lock(config):
        with pytest.raises(TimeoutError):
            with credential_lock(config, timeout=0):
                pytest.fail("lock acquired twice")


def test_missing_refresh_retains_event(environment, monkeypatch):
    config, journal = environment
    cfg = json.loads(config.read_text())
    cfg.pop("refresh_token")
    config.write_text(json.dumps(cfg))
    base.journal_append("{}", "https://api.test")
    calls = []

    def request(req, **_):
        calls.append(req.full_url)
        raise HTTPError(req.full_url, 401, "expired", {}, io.BytesIO())

    monkeypatch.setattr(base.urllib.request, "urlopen", request)
    base.run_drain_daemon()
    assert calls == ["https://api.test/guard/events"]
    assert len(list(journal.glob("*.json"))) == 1


def test_forbidden_is_not_refreshed(environment, monkeypatch):
    _, journal = environment
    base.journal_append("{}", "https://api.test")

    def request(req, **_):
        assert req.full_url.endswith("/guard/events")
        raise HTTPError(req.full_url, 403, "forbidden", {}, io.BytesIO())

    monkeypatch.setattr(base.urllib.request, "urlopen", request)
    base.run_drain_daemon()
    assert len(list((journal / "dead-letter").glob("*.json"))) == 1


def test_refresh_does_not_cross_workspace(environment, monkeypatch):
    config, _ = environment
    snapshot = json.loads(config.read_text())
    config.write_text(json.dumps(dict(snapshot, workspace_id="other")))
    monkeypatch.setattr(auth.urllib.request, "urlopen", lambda *a, **k: pytest.fail("cross-workspace refresh"))
    assert not auth._refresh_agent_token(expected_config=snapshot)
