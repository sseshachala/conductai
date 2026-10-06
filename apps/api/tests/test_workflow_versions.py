"""Workflow version history endpoints + annotation persistence (#2315).

Env (DATABASE_URL etc.) comes from tests/conftest.py.
"""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.auth import get_user_id, get_workspace_id, require_permission
from app.core.database import get_db
from app.dsl import carry_annotations
from app.main import app
from app.schemas.workflow import WorkflowGraph

WS_ID = str(uuid.uuid4())


@pytest.fixture
def client_with_db():
    db = MagicMock()

    def _get_db():
        yield db

    def _noop_permission(perm):
        async def _check():
            return "admin"
        return _check

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_workspace_id] = lambda: WS_ID
    app.dependency_overrides[get_user_id] = lambda: "dev"
    app.dependency_overrides[require_permission] = _noop_permission
    yield TestClient(app, raise_server_exceptions=False), db
    for dep in (get_db, get_workspace_id, get_user_id, require_permission):
        app.dependency_overrides.pop(dep, None)


def _workflow(current_version_id=None):
    wf = MagicMock()
    wf.id = uuid.uuid4()
    wf.current_version_id = current_version_id
    return wf


def test_list_versions_404_when_workflow_not_in_workspace(client_with_db):
    client, db = client_with_db
    db.query.return_value.filter.return_value.first.return_value = None
    res = client.get(f"/workflows/{uuid.uuid4()}/versions")
    assert res.status_code == 404


def test_list_versions_marks_current_and_counts(client_with_db):
    client, db = client_with_db
    current, older = uuid.uuid4(), uuid.uuid4()
    wf = _workflow(current_version_id=current)
    now = datetime.now(timezone.utc)
    rows = [(current, now, False, 3, 2, 1), (older, now, True, 2, 1, 0)]
    wf_query, version_query = MagicMock(), MagicMock()
    wf_query.filter.return_value.first.return_value = wf
    version_query.filter.return_value.order_by.return_value.limit.return_value.all.return_value = rows
    db.query.side_effect = [wf_query, version_query]

    res = client.get(f"/workflows/{wf.id}/versions?limit=10")

    assert res.status_code == 200
    body = res.json()
    assert [v["is_current"] for v in body] == [True, False]
    assert body[0]["node_count"] == 3 and body[0]["annotation_count"] == 1
    assert body[1]["from_yaml"] is True


def test_get_version_404_for_version_of_another_workflow(client_with_db):
    client, db = client_with_db
    wf_query, version_query = MagicMock(), MagicMock()
    wf_query.filter.return_value.first.return_value = _workflow()
    version_query.filter.return_value.first.return_value = None
    db.query.side_effect = [wf_query, version_query]
    res = client.get(f"/workflows/{uuid.uuid4()}/versions/{uuid.uuid4()}")
    assert res.status_code == 404


def test_list_versions_rejects_oversized_limit(client_with_db):
    client, _ = client_with_db
    assert client.get(f"/workflows/{uuid.uuid4()}/versions?limit=10000").status_code == 422


def test_carry_annotations_preserves_notes_across_yaml_rebuild():
    notes = [{"id": "note-1", "type": "annotation", "data": {"text": "why"}}]
    rebuilt = carry_annotations({"nodes": [], "edges": []}, {"nodes": [], "annotations": notes})
    assert rebuilt["annotations"] == notes
    assert carry_annotations({"nodes": []}, None) == {"nodes": []}


def test_graph_schema_keeps_annotations_and_caps_size():
    g = WorkflowGraph(nodes=[], edges=[], annotations=[{"id": "n"}])
    assert g.model_dump()["annotations"] == [{"id": "n"}]
    with pytest.raises(ValidationError):
        WorkflowGraph(annotations=[{"text": "x" * 300_000}])
    with pytest.raises(ValidationError):
        WorkflowGraph(annotations=[{}] * 501)
