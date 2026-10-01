"""Registered-server lifecycle against an explicitly named test database."""
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.auth import check_permission
from app.models.workspace import Workspace
from app.routers.mcp_servers import (
    McpReviewIn,
    McpServerIn,
    create_mcp_server,
    list_mcp_server_tools,
    review_mcp_server,
)
from app.runtime.mcp_credentials import resolve_mcp_server
from app.runtime.mcp_governance import MCPGovernanceDenied


@pytest.fixture
def database():
    url = os.environ.get("DATABASE_URL", "")
    if not url or "test" not in (make_url(url).database or ""):
        pytest.skip("Requires a dedicated test database")
    engine = create_engine(url, connect_args={"connect_timeout": 2})
    try:
        conn = engine.connect()
    except Exception:
        engine.dispose()
        pytest.skip("Test Postgres is not reachable")
    transaction = conn.begin()
    db = Session(bind=conn, join_transaction_mode="create_savepoint")
    workspace = Workspace(name="MCP review fixture", owner_id="fixture-owner")
    db.add(workspace)
    db.flush()
    workspace_id = str(workspace.id)
    try:
        yield db, workspace_id
    finally:
        db.close()
        transaction.rollback()
        conn.close()
        engine.dispose()


def test_enroll_inspect_approve_drift_quarantine_revoke_restore(database, monkeypatch):
    db, ws = database
    tools = [{"name": "read", "description": "Read", "inputSchema": {}}]
    monkeypatch.setattr("app.runtime.integrations.mcp_client.list_tools", lambda *a, **kw: (tools, "http"))
    monkeypatch.setattr("app.routers.mcp_servers._redis_client", lambda: None)
    row = create_mcp_server(McpServerIn(name="review-test", url="https://example.com/mcp",
                                       auth_token="synthetic-test-token"), ws, "admin", db)
    server = row.id

    def change(action, revision, digest=None):
        return review_mcp_server(server, McpReviewIn(action=action, revision=revision, digest=digest),
                                 ws, "fixture-owner", "admin", db)

    change("require_review", 0)
    with pytest.raises(MCPGovernanceDenied):
        resolve_mcp_server(server_id=server, workspace_id=ws, db=db)
    response = Response()
    list_mcp_server_tools(server, ws, "admin", db, response)
    change("approve", 1, response.headers["X-Conduct-MCP-Digest"])
    assert resolve_mcp_server(server_id=server, workspace_id=ws, db=db)[0] == row.url
    tools[0]["description"] = "Changed behavior"
    with pytest.raises(MCPGovernanceDenied, match="changed"):
        resolve_mcp_server(server_id=server, workspace_id=ws, db=db)
    change("quarantine", 2)
    with pytest.raises(HTTPException) as exc:
        list_mcp_server_tools(server, ws, "admin", db)
    assert exc.value.status_code == 403
    revoked = change("revoke", 3)
    assert revoked.has_auth is False
    assert db.execute(text("SELECT encrypted_auth FROM mcp_servers WHERE id = :id"), {"id": server}).scalar_one() is None
    restored = change("restore", 4)
    assert restored.governance["state"] == "needs_review"
    with pytest.raises(MCPGovernanceDenied):
        resolve_mcp_server(server_id=server, workspace_id=ws, db=db)
    count = db.execute(text("SELECT count(*) FROM audit_log WHERE workspace_id = :ws AND resource_id = :id"),
                       {"ws": ws, "id": server}).scalar_one()
    assert count == 5
    with pytest.raises(HTTPException) as exc:
        review_mcp_server(server, McpReviewIn(action="quarantine", revision=5), str(uuid4()), "fixture-owner", "admin", db)
    assert exc.value.status_code == 404


@pytest.mark.parametrize("role", ["viewer", "developer", "security", "admin"])
def test_real_seeded_permissions(database, role):
    db, ws = database
    db.execute(text("INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at) "
                    "VALUES (:ws, :uid, :role, now())"), {"ws": ws, "uid": "fixture-member", "role": role})
    if role == "admin":
        assert check_permission(user_id="fixture-member", workspace_id=ws, credentials=None,
                                db=db, permission="platform.workspace.edit") == "admin"
    else:
        with pytest.raises(HTTPException) as exc:
            check_permission(user_id="fixture-member", workspace_id=ws, credentials=None,
                             db=db, permission="platform.workspace.edit")
        assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ["viewer", "developer", "security", "admin"])
@pytest.mark.parametrize("operation", ["review", "inspect"])
def test_http_permission_matrix(database, real_require_permission, monkeypatch, role, operation):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.core import auth
    from app.core.database import get_db
    from app.routers.mcp_servers import router

    db, ws = database
    db.execute(text("INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at) "
                    "VALUES (:ws, :uid, :role, now())"), {"ws": ws, "uid": "fixture-member", "role": role})
    row = create_mcp_server(McpServerIn(name="http-fixture", url="https://example.com/mcp"), ws, "admin", db)
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[auth.get_user_id] = lambda: "fixture-member"
    app.dependency_overrides[auth.get_workspace_id] = lambda: ws
    app.dependency_overrides[get_db] = lambda: db
    for route in router.routes:
        for dep in route.dependant.dependencies:
            permission = getattr(dep.call, "__conduct_permission__", None)
            if permission:
                app.dependency_overrides[dep.call] = auth.require_permission(permission)
    monkeypatch.setattr("app.runtime.integrations.mcp_client.list_tools", lambda *a, **kw: ([], "http"))
    monkeypatch.setattr("app.routers.mcp_servers._redis_client", lambda: None)
    response = TestClient(app).post(f"/mcp-servers/{row.id}/{operation}",
                                    json={"action": "quarantine", "revision": 0} if operation == "review" else {})
    allowed = role == "admin" if operation == "review" else role in {"admin", "security"}
    assert response.status_code == (200 if allowed else 403)
