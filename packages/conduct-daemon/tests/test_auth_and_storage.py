from __future__ import annotations

import json

from conduct_daemon import daemon, policy_store


def test_headers_use_agent_token(tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"agent_token": "cond_agt_test"}))
    monkeypatch.setattr(daemon, "CONFIG_PATH", config)

    assert daemon._headers() == {"Authorization": "Bearer cond_agt_test"}


def test_database_uses_conduct_home(tmp_path, monkeypatch):
    current = tmp_path / ".conduct" / "daemon.db"
    monkeypatch.setattr(policy_store, "_DB_PATH", current)
    policy_store.init_db()
    policy_store.queue_event("workspace", {"workspace_id": "workspace"})

    assert current.exists()
    assert current.stat().st_mode & 0o777 == 0o600
    assert policy_store.drain_events() == [{"workspace_id": "workspace"}]
