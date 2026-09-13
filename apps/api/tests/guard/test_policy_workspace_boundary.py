"""Policy mutations must stay inside the authenticated workspace."""
from unittest.mock import MagicMock

from fastapi.testclient import TestClient


def test_create_policy_rejects_foreign_workspace_in_body():
    from app.core.auth import get_user_id, get_workspace_id
    from app.core.database import get_db
    from app.main import app

    authorized_workspace = "00000000-0000-0000-0000-000000000001"
    foreign_workspace = "00000000-0000-0000-0000-000000000002"
    app.dependency_overrides[get_db] = lambda: MagicMock()
    app.dependency_overrides[get_workspace_id] = lambda: authorized_workspace
    app.dependency_overrides[get_user_id] = lambda: "user_test"
    try:
        response = TestClient(app, raise_server_exceptions=False).post(
            "/guard/policies",
            json={
                "rule_id": "must-not-cross-workspaces",
                "action": "block",
                "workspace_id": foreign_workspace,
            },
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Policy workspace does not match authorized workspace"
    finally:
        app.dependency_overrides.clear()
