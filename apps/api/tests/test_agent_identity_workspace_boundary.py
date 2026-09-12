"""Agent-identity routes must bind path scope to authorized workspace scope."""
from unittest.mock import MagicMock, patch

import pytest
from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.modules.agent_identity.router import create_agent_identity, list_run_tokens, router
from app.modules.agent_identity.schemas import AgentIdentityCreate
from fastapi import FastAPI, HTTPException
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


def test_cross_workspace_environment_is_rejected_before_identity_write():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    body = AgentIdentityCreate(name="isolated", environment_id=OTHER_WORKSPACE_ID)

    with patch("app.modules.agent_identity.router._generate_token", return_value=("token", "prefix")), \
         patch("app.modules.agent_identity.router.encrypt", return_value="encrypted"), \
         pytest.raises(HTTPException, match="Environment not found"):
        create_agent_identity(WORKSPACE_ID, body, _ws=WORKSPACE_ID, _="admin", db=db)

    db.add.assert_not_called()
    db.execute.assert_not_called()
    db.commit.assert_not_called()


def test_cross_workspace_identity_reference_is_rejected_before_token_query():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException, match="Agent identity not found"):
        list_run_tokens(WORKSPACE_ID, OTHER_WORKSPACE_ID, _ws=WORKSPACE_ID, _="admin", db=db)

    assert db.query.call_count == 1
    db.commit.assert_not_called()
