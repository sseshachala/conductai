from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.auth import get_user_id, get_workspace_id
from app.core.database import get_db
from app.routers.whoami import router


@pytest.mark.parametrize("state,expected", [("active", "agent-a"), ("deactivated", None), ("expired", None)])
def test_linked_cli_identity_is_scoped_to_current_member_and_workspace(state, expected):
    app, db = FastAPI(), MagicMock()
    app.include_router(router)
    app.dependency_overrides[get_workspace_id] = lambda: "workspace-a"
    app.dependency_overrides[get_user_id] = lambda: "member-a"
    app.dependency_overrides[get_db] = lambda: db
    db.query.return_value.join.return_value.filter.return_value.first.return_value = SimpleNamespace(
        id="agent-a", name="Build bot", lifecycle_state=state,
    )
    response = TestClient(app).get("/auth/cli-identity")
    assert response.status_code == 200
    result = response.json()
    assert result["workspace_id"] == "workspace-a"
    assert (result["identity"]["id"] if result["identity"] else None) == expected
    filters = db.query.return_value.join.return_value.filter.call_args.args
    assert [condition.right.value for condition in (filters[0], filters[1], filters[3])] == [
        "workspace-a", "member-a", "workspace-a",
    ]
    db.add.assert_not_called(); db.commit.assert_not_called()


def test_cli_identity_requires_authenticated_member_dependencies():
    route = next(r for r in router.routes if r.path.endswith("/cli-identity"))
    assert {d.call for d in route.dependant.dependencies} >= {get_user_id, get_workspace_id}
