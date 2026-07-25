"""Fix for #985: endpoints must return clean 401 (not 500) when the caller is
authenticated as an agent token with no linked Clerk user.

Two categories:
  - user-only endpoints (rename/delete project) → 401 with clear message
  - workspace-scoped endpoints (list runs) → 200 (agents are legitimate callers)
"""
import os
import uuid
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test_marshal")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

import app.models.environment  # noqa: F401
import app.models.project      # noqa: F401
import app.models.run          # noqa: F401
import app.models.workspace    # noqa: F401

from fastapi.testclient import TestClient

from app.main import app
from app.core.database import get_db
from app.core.auth import get_workspace_id, get_user_id, require_permission

WS_ID = str(uuid.uuid4())
PROJECT_ID = str(uuid.uuid4())


def _override_db(db_mock):
    def _get_db():
        yield db_mock
    return _get_db


def _make_client(db_mock, user_id):
    """Return a TestClient where get_user_id yields the given value (None simulates
    an unlinked agent/api token)."""
    def _noop_permission(perm):
        async def _check():
            return "admin"
        return _check

    app.dependency_overrides[get_db] = _override_db(db_mock)
    app.dependency_overrides[get_workspace_id] = lambda: WS_ID
    app.dependency_overrides[get_user_id] = lambda: user_id
    app.dependency_overrides[require_permission] = _noop_permission
    return TestClient(app, raise_server_exceptions=False)


def _teardown():
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_workspace_id, None)
    app.dependency_overrides.pop(get_user_id, None)
    app.dependency_overrides.pop(require_permission, None)


# ── User-only endpoints must return 401 for unlinked agent tokens ────────────

def test_rename_project_returns_401_when_user_id_is_none():
    """PATCH /projects/{id} with an agent token that has no linked Clerk user
    must return 401 (not the previous 500 from downstream None handling)."""
    db_mock = MagicMock()
    client = _make_client(db_mock, user_id=None)
    try:
        r = client.patch(f"/projects/{PROJECT_ID}", json={"name": "new"})
        assert r.status_code == 401, r.text
        assert "Clerk user session" in r.json().get("detail", "")
    finally:
        _teardown()


def test_delete_project_returns_401_when_user_id_is_none():
    """DELETE /projects/{id} with an agent token that has no linked Clerk user
    must return 401 (not the previous 500)."""
    db_mock = MagicMock()
    client = _make_client(db_mock, user_id=None)
    try:
        r = client.delete(f"/projects/{PROJECT_ID}")
        assert r.status_code == 401, r.text
        assert "Clerk user session" in r.json().get("detail", "")
    finally:
        _teardown()


# ── Workspace-scoped endpoints work with agent tokens (already correct) ──────

def test_list_runs_works_with_agent_token():
    """GET /workflows/{id}/runs uses get_workspace_id (not get_user_id), so an
    agent token that resolves a workspace works fine — lock this in."""
    from app.models.workflow import Workflow

    db_mock = MagicMock()
    # _get_workflow queries Workflow by id + workspace scope; return a stub
    fake_wf = MagicMock(spec=Workflow)
    fake_wf.id = uuid.uuid4()
    fake_wf.workspace_id = uuid.UUID(WS_ID)
    fake_wf.current_version_id = uuid.uuid4()
    fake_wf.archived_at = None
    db_mock.query.return_value.filter.return_value.first.return_value = fake_wf
    db_mock.query.return_value.filter.return_value.subquery.return_value = MagicMock()
    db_mock.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    # Agent token path: user_id may be present (linked) or None (unlinked); either
    # should be fine because the endpoint doesn't depend on user_id.
    client = _make_client(db_mock, user_id=None)
    try:
        r = client.get(f"/workflows/{fake_wf.id}/runs")
        assert r.status_code == 200, r.text
        assert r.json() == []
    finally:
        _teardown()
