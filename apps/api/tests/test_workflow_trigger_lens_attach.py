"""#1515 P1 — canvas Run trigger with lens_attach=True.

Verifies the trigger endpoint auto-mints a Lens session, sets
Run.session_id, and appends a run_started envelope to session messages
so RunBubble rehydrates on session load.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.database import get_db
from app.main import app


class _DummyRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def rpush(self, key: str, value: str) -> None:
        self.calls.append((key, value))


class _FakeQuery:
    def __init__(self, result=None) -> None:
        self._result = result

    def filter(self, *_a, **_kw):
        return self

    def first(self):
        return self._result


class _FakeDB:
    """Routes queries by model class — Workflow lookup returns the stub;
    GlensChatSession lookup returns whatever was last added of that type."""

    def __init__(self, workflow) -> None:
        self.workflow = workflow
        self.added: list[object] = []
        self._by_type: dict[str, list] = {}

    def add(self, obj) -> None:
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        self.added.append(obj)
        self._by_type.setdefault(type(obj).__name__, []).append(obj)

    def commit(self) -> None:
        return None

    def flush(self) -> None:
        return None

    def refresh(self, obj) -> None:
        return None

    def rollback(self) -> None:
        return None

    def execute(self, *_a, **_kw):
        return None

    def query(self, model):
        name = getattr(model, "__name__", "")
        if name == "Workflow":
            return _FakeQuery(result=self.workflow)
        # GlensChatSession — return the last one added (matches the .id filter).
        rows = self._by_type.get(name, [])
        return _FakeQuery(result=rows[-1] if rows else None)


def _workflow_stub(workflow_id: str, workspace_id: str) -> SimpleNamespace:
    version_id = uuid.uuid4()
    return SimpleNamespace(
        id=uuid.UUID(workflow_id),
        workspace_id=uuid.UUID(workspace_id),
        current_version_id=version_id,
        current_version=SimpleNamespace(
            id=version_id,
            graph={"nodes": [{"id": "t1", "data": {"type": "trigger", "config": {"repo_allowlist": "my-org/my-repo"}}}]},
            yaml_source=None,
        ),
        playbook_slug=None,
        github_hook_repo=None,
        default_max_turns=None,
        name="Test Workflow",
    )


def test_trigger_with_lens_attach_mints_session_and_sets_run_session_id(monkeypatch):
    from app.routers import workflows as workflows_router
    import redis

    workspace_id = "00000000-0000-0000-0000-000000000001"
    workflow_id = "44444444-4444-4444-4444-444444444444"
    workflow = _workflow_stub(workflow_id, workspace_id)
    db = _FakeDB(workflow=workflow)
    redis_stub = _DummyRedis()

    monkeypatch.setattr(workflows_router, "_estimate_turns_for_graph", lambda *a, **kw: {"suggested_max_turns": 12})
    monkeypatch.setattr(redis, "from_url", lambda *_a, **_kw: redis_stub)

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/workflows/{workflow_id}/trigger",
            json={
                "lens_attach": True,
                "issue": {"number": 1, "title": "t", "body": "", "html_url": "", "user": {"login": "u"}, "labels": []},
                "repository": {"full_name": "my-org/my-repo", "name": "my-repo", "owner": {"login": "my-org"}, "default_branch": "main", "clone_url": "", "_caller_set": True},
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_id"], "response must include session_id when lens_attach=true"

    # Exactly one GlensChatSession minted, exactly one Run added.
    sessions = [o for o in db.added if type(o).__name__ == "GlensChatSession"]
    runs = [o for o in db.added if type(o).__name__ == "Run"]
    assert len(sessions) == 1, f"expected 1 session, got {len(sessions)}"
    assert len(runs) == 1, f"expected 1 run, got {len(runs)}"

    # Run.session_id must match the minted session id (this is the seam the
    # SSE publisher needs — publish no-ops on session_id=NULL).
    assert runs[0].session_id == sessions[0].id
    assert body["session_id"] == str(sessions[0].id)

    # Session must carry a run_started envelope so RunBubble rehydrates.
    messages = json.loads(sessions[0].messages)
    assert len(messages) == 1
    envelope = json.loads(messages[0]["content"])
    assert envelope["run_started"]["run_id"] == str(runs[0].id)
    assert envelope["run_started"]["workflow_name"] == "Test Workflow"


def test_trigger_without_lens_attach_omits_session(monkeypatch):
    """Baseline: CLI/webhook callers don't set lens_attach — session_id stays None."""
    from app.routers import workflows as workflows_router
    import redis

    workspace_id = "00000000-0000-0000-0000-000000000001"
    workflow_id = "55555555-5555-5555-5555-555555555555"
    workflow = _workflow_stub(workflow_id, workspace_id)
    db = _FakeDB(workflow=workflow)
    redis_stub = _DummyRedis()

    monkeypatch.setattr(workflows_router, "_estimate_turns_for_graph", lambda *a, **kw: {"suggested_max_turns": 12})
    monkeypatch.setattr(redis, "from_url", lambda *_a, **_kw: redis_stub)

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/workflows/{workflow_id}/trigger",
            json={
                "issue": {"number": 1, "title": "t", "body": "", "html_url": "", "user": {"login": "u"}, "labels": []},
                "repository": {"full_name": "my-org/my-repo", "name": "my-repo", "owner": {"login": "my-org"}, "default_branch": "main", "clone_url": "", "_caller_set": True},
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["session_id"] is None
    sessions = [o for o in db.added if type(o).__name__ == "GlensChatSession"]
    assert sessions == []
    runs = [o for o in db.added if type(o).__name__ == "Run"]
    assert runs and runs[0].session_id is None
