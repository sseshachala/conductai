"""Agent-identity routes must bind path scope to authorized workspace scope."""
from unittest.mock import MagicMock

import pytest
from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.modules.agent_identity.router import router
from fastapi import FastAPI
from fastapi.testclient import TestClient

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
OTHER_WORKSPACE_ID = "22222222-2222-4222-8222-222222222222"


@pytest.mark.parametrize("route", router.routes, ids=lambda route: route.name)
def test_every_identity_route_denies_conflicting_path_before_database_access(route):
    app = FastAPI()
    app.include_router(router)
    db = MagicMock()
    app.dependency_overrides[get_workspace_id] = lambda: WORKSPACE_ID
    app.dependency_overrides[get_db] = lambda: db
    path = route.path.format(
        workspace_id=OTHER_WORKSPACE_ID,
        identity_id=WORKSPACE_ID,
        token_id=WORKSPACE_ID,
    )

    with TestClient(app) as client:
        response = client.request(next(iter(route.methods)), path, json={"name": "test"})

    assert response.status_code == 403
    assert response.json()["detail"] == "Workspace path does not match authorized workspace"
    assert db.mock_calls == []


def test_matching_workspace_reaches_identity_list():
    app = FastAPI()
    app.include_router(router)
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    app.dependency_overrides[get_workspace_id] = lambda: WORKSPACE_ID
    app.dependency_overrides[get_db] = lambda: db

    with TestClient(app) as client:
        response = client.get(f"/workspaces/{WORKSPACE_ID}/agent-identities")

    assert response.status_code == 200
    assert response.json() == []
