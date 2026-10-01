from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.core import auth
from app.core.database import get_db
from app.models.mcp_server import McpServer
from app.models.workspace import Workspace
from app.modules.guard.models import DiscoveredAgent
from app.modules.guard.routers.discovery import ScanIn, ingest_scan, router
from app.modules.guard.routers.mcp_reconciliation import McpLinkIn, link_registration, list_reconciliation, router as links_router
from tests.test_mcp_governance_db import database  # noqa: F401 - shared disposable transaction fixture

REF = "b" * 64


def seed(db, ws):
    device = uuid4()
    scan = ScanIn(schema_version=2, device_id=device, agents=[{
        "framework": "codex", "installation_id": "a" * 64, "detection": "installed",
        "evidence": {"mcp_servers": [{"id": REF, "name": "docs", "scope": "user", "transport": "stdio"}]},
    }])
    agent = UUID(ingest_scan(scan, ws, db)["agents"][0]["id"])
    server = McpServer(workspace_id=UUID(ws), name="fixture", url="https://private.invalid",
                       encrypted_auth="synthetic-private", governance={"state": "quarantined", "revision": 1})
    db.add(server)
    db.commit()
    return agent, server, scan


def link(db, ws, agent, server, revision=0, reference=REF):
    return link_registration(agent, reference, McpLinkIn(server_id=server, revision=revision), ws, "fixture-owner", "admin", db)


def test_link_scan_preservation_review_changes_and_unlink(database):
    db, ws = database
    agent, server, scan = seed(db, ws)
    result = link(db, ws, agent, server.id)
    assert result["servers"][0]["registration"]["review_status"] == "quarantined"
    assert result["servers"][0]["enforcement_status"] == "not_observed"
    scan.agents[0].evidence["mcp_links"] = {"bindings": {REF: {"server_id": str(uuid4())}}}
    ingest_scan(scan, ws, db)
    result = list_reconciliation(ws, "viewer", db, 100, 0)
    assert result["installations"][0]["revision"] == 1
    assert result["registrations"][0]["id"] == str(server.id)
    assert "private" not in str(result)
    with pytest.raises(HTTPException) as exc:
        link(db, ws, agent, server.id)
    assert exc.value.status_code == 409
    result = link(db, ws, agent, None, 1)
    assert result["servers"][0]["registration_status"] == "unlinked"
    actions = db.execute(text("SELECT action FROM audit_log WHERE workspace_id=:ws ORDER BY created_at"), {"ws": ws}).scalars().all()
    assert actions == ["mcp.inventory.linked", "mcp.inventory.unlinked"]


def test_cross_workspace_and_missing_reference_rejected(database):
    db, ws = database
    agent, server, _ = seed(db, ws)
    other = Workspace(name="other")
    db.add(other)
    db.flush()
    foreign = McpServer(workspace_id=other.id, name="foreign", url="https://foreign.invalid")
    db.add(foreign)
    db.commit()
    for target_ws, target_server, reference in [(str(other.id), server.id, REF), (ws, foreign.id, REF), (ws, server.id, "c" * 64)]:
        with pytest.raises(HTTPException) as exc:
            link(db, target_ws, agent, target_server, reference=reference)
        assert exc.value.status_code == 404
        db.rollback()
    result = list_reconciliation(ws, "viewer", db, 100, 0)
    assert "foreign" not in str(result)


def test_missing_registration_and_removed_reference_can_be_unlinked(database):
    db, ws = database
    agent, server, scan = seed(db, ws)
    link(db, ws, agent, server.id)
    db.delete(server)
    db.commit()
    scan.agents[0].evidence = {"mcp_servers": []}
    ingest_scan(scan, ws, db)
    finding = list_reconciliation(ws, "viewer", db, 100, 0)["installations"][0]["servers"][0]
    assert finding["registration_status"] == "registration_missing"
    assert finding["discovery_status"] == "not_reported"
    assert link(db, ws, agent, None, 1)["servers"] == []


def test_stale_scan_refuses_new_link(database):
    db, ws = database
    agent, server, _ = seed(db, ws)
    row = db.get(DiscoveredAgent, agent)
    row.last_seen_at = datetime.now(timezone.utc) - timedelta(days=2)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        link(db, ws, agent, server.id)
    assert exc.value.status_code == 409


def test_pagination_and_link_limit(database):
    db, ws = database
    agent, server, scan = seed(db, ws)
    scan.device_id = uuid4()
    ingest_scan(scan, ws, db)
    first = list_reconciliation(ws, "viewer", db, 1, 0)
    second = list_reconciliation(ws, "viewer", db, 1, first["next_offset"])
    assert first["installations"][0]["agent_id"] != second["installations"][0]["agent_id"]
    assert second["next_offset"] is None
    row = db.get(DiscoveredAgent, agent)
    row.mcp_links = {"revision": 1, "bindings": {f"{i:064x}": {"server_id": str(server.id)} for i in range(100)}}
    db.commit()
    with pytest.raises(HTTPException) as exc:
        link(db, ws, agent, server.id, 1)
    assert exc.value.status_code == 409


@pytest.mark.parametrize("role", ["admin", "security", "developer", "viewer", None])
def test_http_permission_matrix(database, real_require_permission, role):
    db, ws = database
    agent, server, _ = seed(db, ws)
    if role:
        db.execute(text("INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at) VALUES (:ws, 'member', :role, now())"),
                   {"ws": ws, "role": role})
    db.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[auth.get_user_id] = lambda: "member"
    app.dependency_overrides[auth.get_workspace_id] = lambda: ws
    app.dependency_overrides[get_db] = lambda: db
    for route in links_router.routes:
        for dep in route.dependant.dependencies:
            permission = getattr(dep.call, "__conduct_permission__", None)
            if permission:
                app.dependency_overrides[dep.call] = auth.require_permission(permission)
    client = TestClient(app)
    assert client.get("/guard/discover/mcp-reconciliation").status_code == (200 if role else 403)
    response = client.put(f"/guard/discover/agents/{agent}/mcp-links/{REF}", json={"server_id": str(server.id), "revision": 0})
    assert response.status_code == (200 if role == "admin" else 403)


def test_migration_refuses_to_drop_admin_associations(database):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    db, ws = database
    agent, server, _ = seed(db, ws)
    link(db, ws, agent, server.id)
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0160_mcp_inventory_links.py"
    spec = importlib.util.spec_from_file_location("mcp_links_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with pytest.raises(RuntimeError, match="data-preserving"):
        with Operations.context(MigrationContext.configure(db.connection())):
            migration.downgrade()
    assert db.get(DiscoveredAgent, agent).mcp_links["revision"] == 1
