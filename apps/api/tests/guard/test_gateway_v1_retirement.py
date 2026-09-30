import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.auth import get_workspace_id
from app.core.database import get_db
from app.routers import gateways

ROUTES = [
    ("GET", ""), ("GET", "/profile"), ("POST", ""),
    ("PUT", "/profile"), ("DELETE", "/profile"),
    ("POST", "/validate"), ("POST", "/profile/push"),
]


def client(permission_status=None):
    app = FastAPI()
    app.include_router(gateways.router)
    app.dependency_overrides[get_workspace_id] = lambda: "workspace"

    def permission():
        if permission_status:
            raise HTTPException(permission_status, "Denied")
        return "user"

    def database():
        raise AssertionError("Retired routes must not access or mutate profile data")

    app.dependency_overrides[get_db] = database
    for route in gateways.router.routes:
        for dependency in route.dependant.dependencies:
            if dependency.call is not get_workspace_id:
                app.dependency_overrides[dependency.call] = permission
    return TestClient(app)


@pytest.mark.parametrize("method,suffix", ROUTES)
def test_retired_routes_return_410_without_touching_v1_or_v2_data(method, suffix):
    response = client().request(method, f"/workspaces/workspace/gateways{suffix}")
    assert response.status_code == 410
    assert response.json()["detail"]["code"] == "gateway_v1_retired"
    assert response.json()["detail"]["replacement"].endswith("/gateway-profiles-v2")


@pytest.mark.parametrize("method,suffix", ROUTES)
def test_retirement_keeps_workspace_boundary(method, suffix):
    assert client().request(method, f"/workspaces/foreign/gateways{suffix}").status_code == 403


@pytest.mark.parametrize("status", [401, 403])
@pytest.mark.parametrize("method,suffix", ROUTES)
def test_retirement_keeps_auth_and_permission_checks(method, suffix, status):
    assert client(status).request(method, f"/workspaces/workspace/gateways{suffix}").status_code == status
