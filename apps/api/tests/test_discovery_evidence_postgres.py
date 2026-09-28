"""Opt-in real migration and inventory contract tests in disposable schemas."""
import importlib.util
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateSchema, DropSchema

from app.modules.guard.models import DiscoveryScan, DiscoveredAgent
from app.models.workspace import Workspace  # register FK metadata
from app.modules.guard.discovery_inventory import observe_hook, workspace_inventory
from app.modules.guard.routers.discovery import ScanIn, ingest_scan, register_agent

WS = uuid.UUID("11111111-1111-4111-8111-111111111111")


@pytest.fixture
def database():
    url = os.environ.get("DISCOVERY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("DISCOVERY_TEST_DATABASE_URL not set")
    schema = "discovery_test_" + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(CreateSchema(schema))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE workspaces (id uuid PRIMARY KEY)"))
            conn.execute(text("INSERT INTO workspaces VALUES (:id)"), {"id": WS})
            DiscoveryScan.__table__.create(conn)
            conn.execute(text("""CREATE TABLE discovered_agents (
                id uuid PRIMARY KEY, workspace_id uuid NOT NULL REFERENCES workspaces(id),
                scan_id uuid REFERENCES discovery_scans(id), name text, framework varchar(50), source varchar(20),
                location text, evidence jsonb, risk_score integer, under_guard boolean NOT NULL,
                proxy_routed boolean NOT NULL, first_seen_at timestamptz NOT NULL, last_seen_at timestamptz NOT NULL,
                CONSTRAINT uq_discovered_agents_workspace_framework_source UNIQUE(workspace_id, framework, source))"""))
            conn.execute(text("CREATE TABLE guard_knowledge_index (source_kind text)"))
            conn.execute(text("""INSERT INTO discovered_agents VALUES (:id,:ws,NULL,'legacy','codex','config',
                '/unsafe/path','{"cmdline":"unsafe"}',60,true,true,now(),now())"""), {"id": uuid.uuid4(), "ws": WS})
            path = Path(__file__).resolve().parents[1] / "alembic/versions/0153_discovery_evidence.py"
            spec = importlib.util.spec_from_file_location("discovery_migration", path)
            migration = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(migration)
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def scan(device, **kw):
    return ScanIn(schema_version=2, device_id=device, agents=[{
        "framework": "codex", "installation_id": "a" * 64, "detection": "installed",
        "evidence": {"hooks_configured": True, "cmdline": "must-not-persist"},
    }], **kw)


def test_migration_invalidates_legacy_claims(database):
    with Session(database) as db:
        row = db.query(DiscoveredAgent).one()
        assert row.evidence is row.location is None
        assert not row.under_guard and not row.proxy_routed
        assert workspace_inventory(db, WS)[0]["detection"] == "legacy_unverified"


def test_repeat_scan_preserves_identity_and_hook_but_separates_devices(database):
    device = uuid.uuid4()
    with Session(database) as db:
        first = ingest_scan(scan(device), str(WS), db)["agents"][0]
        event = uuid.uuid4()
        observe_hook(db, WS, device, "a" * 64, "codex", event, datetime.now(timezone.utc))
        db.commit()
        second = ingest_scan(scan(device), str(WS), db)["agents"][0]
        assert second["id"] == first["id"]
        assert second["hook_event_id"] == str(event)
        assert second["hooks_status"] == "observed"
        assert "cmdline" not in second["evidence"]
        third = ingest_scan(scan(uuid.uuid4()), str(WS), db)["agents"][0]
        assert third["id"] != first["id"]
        assert third["hooks_status"] == "configured"


def test_failed_scan_does_not_replace_inventory_and_register_cannot_protect(database):
    device = uuid.uuid4()
    with Session(database) as db:
        first = ingest_scan(scan(device), str(WS), db)["agents"][0]
        result = ingest_scan(scan(device, status="failed"), str(WS), db)
        assert result["agents"] == []
        assert db.query(DiscoveredAgent).filter_by(device_id=device).one().last_seen_at == first["last_seen_at"]
        with pytest.raises(HTTPException) as error:
            register_agent(uuid.UUID(first["id"]), str(WS), db)
        assert error.value.status_code == 409
        assert not db.query(DiscoveredAgent).filter_by(device_id=device).one().under_guard


def test_workspace_boundary_and_legacy_upsert(database):
    with Session(database) as db:
        other = uuid.uuid4()
        db.execute(text("INSERT INTO workspaces VALUES (:id)"), {"id": other})
        db.commit()
        result = ingest_scan(scan(uuid.uuid4()), str(other), db)
        assert all(a["id"] != result["agents"][0]["id"] for a in workspace_inventory(db, WS))
        with pytest.raises(HTTPException) as error:
            register_agent(uuid.UUID(result["agents"][0]["id"]), str(WS), db)
        assert error.value.status_code == 404
        legacy = ScanIn(agents=[{"framework": "codex", "source": "config", "under_guard": True}])
        one = ingest_scan(legacy, str(WS), db)
        two = ingest_scan(legacy, str(WS), db)
        assert one["agents"][0]["id"] == two["agents"][0]["id"]
        assert two["agents"][0]["hooks_status"] == "unverified"


def test_lens_mcp_and_api_share_evidence(database, monkeypatch):
    import json
    from types import SimpleNamespace
    from app.core import database as database_module
    from app.tools.registrations.lens.discovery import get_discovery_summary
    from app.modules.guard.mcp_impls import guard_discover_impl
    device = uuid.uuid4()
    with Session(database) as db:
        ingest_scan(scan(device), str(WS), db)
        observe_hook(db, WS, device, "a" * 64, "codex", uuid.uuid4(), datetime.now(timezone.utc))
        db.commit()
        monkeypatch.setattr(database_module, "SessionLocal", lambda: Session(database))
        ctx = SimpleNamespace(workspace_id=str(WS), ws_uuid=WS, db=db)
        lens = get_discovery_summary(ctx)
        mcp = json.loads(guard_discover_impl(ctx))
        api = workspace_inventory(db, WS)
        for result in (lens, mcp):
            assert result["recent_hook_evidence"] == 1
            assert [(a["id"], a["hooks_status"]) for a in result["agents"]] == [(a["id"], a["hooks_status"]) for a in api]


def test_old_writer_conflict_target_survives_migration(database):
    with Session(database) as db:
        db.execute(text("""INSERT INTO discovered_agents
            (id,workspace_id,framework,source,under_guard,proxy_routed,first_seen_at,last_seen_at)
            VALUES (:id,:ws,'codex','config',true,true,now(),now())
            ON CONFLICT (workspace_id,framework,source) DO UPDATE SET under_guard=true"""), {"id": uuid.uuid4(), "ws": WS})
        db.commit()
        assert workspace_inventory(db, WS)[0]["hooks_status"] == "unverified"


def migration_module():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0153_discovery_evidence.py"
    spec = importlib.util.spec_from_file_location("discovery_rollback_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_downgrade_upgrade_cycle_preserves_legacy_rows(database):
    from sqlalchemy import inspect
    migration = migration_module()
    with database.begin() as conn:
        before = conn.execute(text("SELECT id FROM discovered_agents")).scalars().all()
        with Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        assert "device_id" not in {c["name"] for c in inspect(conn).get_columns("discovered_agents")}
        assert conn.execute(text("SELECT id FROM discovered_agents")).scalars().all() == before
        with Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        assert "device_id" in {c["name"] for c in inspect(conn).get_columns("discovered_agents")}
        assert conn.execute(text("SELECT id FROM discovered_agents")).scalars().all() == before


@pytest.mark.parametrize("column,value", [
    ("device_id", str(uuid.uuid4())), ("installation_id", "a" * 64),
    ("detection", "installed"), ("hook_observed_at", datetime.now(timezone.utc)),
    ("hook_event_id", str(uuid.uuid4())),
])
def test_downgrade_refuses_any_installation_evidence(database, column, value):
    migration = migration_module()
    with database.begin() as conn:
        conn.execute(text(f"UPDATE discovered_agents SET {column} = :value"), {"value": value})
    with pytest.raises(RuntimeError, match="data-preserving rollback"):
        with database.begin() as conn:
            with Operations.context(MigrationContext.configure(conn)):
                migration.downgrade()
    with database.connect() as conn:
        assert conn.execute(text(f"SELECT {column} FROM discovered_agents")).scalar_one() is not None
