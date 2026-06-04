from __future__ import annotations

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
    def __init__(self, first_result=None, all_result=None) -> None:
        self._first = first_result
        self._all = all_result or []

    def filter(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def first(self):
        return self._first

    def all(self):
        return self._all


class _FakeDB:
    def __init__(self, workflow=None) -> None:
        self.workflow = workflow
        self.added: list[object] = []

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)
        self.added.append(obj)

    def commit(self):
        return None

    def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()
        if getattr(obj, "created_at", None) is None:
            obj.created_at = datetime.now(timezone.utc)

    def query(self, _model):
        return _FakeQuery(first_result=self.workflow)


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
    )


def test_create_run_rejects_invalid_initial_state(monkeypatch):
    from app.routers import runs as runs_router

    workspace_id = "00000000-0000-0000-0000-000000000001"
    workflow_id = "11111111-1111-1111-1111-111111111111"
    workflow = _workflow_stub(workflow_id, workspace_id)
    db = _FakeDB(workflow=workflow)

    monkeypatch.setattr(runs_router, "_get_workflow", lambda *_args, **_kwargs: workflow)
    monkeypatch.setattr(runs_router, "_redis", lambda: _DummyRedis())
    monkeypatch.setattr(runs_router, "audit", lambda *args, **kwargs: None)

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/workflows/{workflow_id}/runs",
            json={"initial_state": {}, "max_turns": 5},
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 422


def test_create_run_returns_explainability_and_governance(monkeypatch):
    from app.routers import runs as runs_router

    workspace_id = "00000000-0000-0000-0000-000000000001"
    workflow_id = "22222222-2222-2222-2222-222222222222"
    workflow = _workflow_stub(workflow_id, workspace_id)
    db = _FakeDB(workflow=workflow)
    redis_stub = _DummyRedis()

    monkeypatch.setattr(runs_router, "_get_workflow", lambda *_args, **_kwargs: workflow)
    monkeypatch.setattr(runs_router, "_redis", lambda: redis_stub)
    monkeypatch.setattr(runs_router, "audit", lambda *args, **kwargs: None)

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/workflows/{workflow_id}/runs",
            json={
                "triggered_by": "manual",
                "max_turns": 7,
                "initial_state": {"_trigger": {"event_type": "manual", "action": "start"}},
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["explainability"]["source"] == "manual"
    assert body["explainability"]["trigger_provider"] == "manual"
    assert body["explainability"]["budget"]["max_turns"] == 7
    assert body["governance"]["policy_surface"] == "unified"
    assert body["governance"]["enforcement_mode"] == "consistent"
    assert redis_stub.calls


def test_workflow_trigger_stamps_github_governance_contract(monkeypatch):
    from app.routers import workflows as workflows_router
    import redis

    workspace_id = "00000000-0000-0000-0000-000000000001"
    workflow_id = "33333333-3333-3333-3333-333333333333"
    workflow = _workflow_stub(workflow_id, workspace_id)
    db = _FakeDB(workflow=workflow)
    redis_stub = _DummyRedis()

    monkeypatch.setattr(workflows_router, "_estimate_turns_for_graph", lambda *args, **kwargs: {"suggested_max_turns": 12})
    monkeypatch.setattr(redis, "from_url", lambda *_args, **_kwargs: redis_stub)

    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            f"/workflows/{workflow_id}/trigger",
            json={
                "__max_turns_override": 15,
                "label": {"name": "autopilot-ready"},
                "issue": {
                    "number": 42,
                    "title": "Fix build",
                    "body": "Please fix failing pipeline",
                    "html_url": "https://github.com/my-org/my-repo/issues/42",
                    "user": {"login": "alice"},
                    "labels": [{"name": "autopilot-ready"}],
                },
                "repository": {
                    "full_name": "my-org/my-repo",
                    "name": "my-repo",
                    "owner": {"login": "my-org"},
                    "default_branch": "main",
                    "clone_url": "https://github.com/my-org/my-repo.git",
                    "_caller_set": True,
                },
            },
        )
    finally:
        app.dependency_overrides.pop(get_db, None)

    assert response.status_code == 200, response.text
    assert response.json()["max_turns"] == 15

    run = db.added[-1]
    state = run.state
    assert state["__governance"]["provider"] == "github"
    assert state["__run_explainability"]["source"] == "manual:test_trigger"
    assert state["__run_explainability"]["budget"]["max_turns"] == 15
    assert redis_stub.calls


def test_retry_boundary_classification_is_deterministic_for_turn_cap():
    from app.runtime.executor import _classify_failure

    summary = _classify_failure(
        RuntimeError("Turn budget exhausted: agent did not reach end_turn after 20 turns")
    )

    assert summary["code"] == "RETRY_BUDGET_EXHAUSTED"
    assert summary["stop_reason"] == "max_turns_reached"
    assert "increase the run turn budget" in summary["next_action"]


def test_retry_boundary_classification_is_deterministic_for_cost_cap():
    from app.runtime.executor import _classify_failure

    summary = _classify_failure(
        RuntimeError("Cost budget exhausted: agent reached $5.3000 with cap $5.0000 after 6 turns")
    )

    assert summary["code"] == "COST_BUDGET_EXHAUSTED"
    assert summary["stop_reason"] == "max_cost_reached"
    assert "raise the cost cap" in summary["next_action"]
