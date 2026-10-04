"""Real PostgreSQL coverage for migration 0164 and tenant constraints."""

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import settings


@pytest.fixture
def projection_database():
    if os.environ.get("PROJECTION_QUEUE_REAL_TESTS") != "1":
        pytest.skip("Set PROJECTION_QUEUE_REAL_TESTS=1 for PostgreSQL checks")
    schema = "projection_queue_" + uuid4().hex
    role = "projection_queue_role_" + uuid4().hex
    admin = create_engine(settings.sqlalchemy_database_url)
    engine = create_engine(
        settings.sqlalchemy_database_url,
        connect_args={"options": f"-csearch_path={schema}"},
    )
    workspace_id, other_workspace_id = uuid4(), uuid4()
    path = (
        Path(__file__).resolve().parents[2]
        / "alembic/versions/0164_guard_projection_intents.py"
    )
    spec = importlib.util.spec_from_file_location("projection_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with admin.begin() as conn:
        conn.execute(CreateSchema(schema))
        conn.execute(text(f'CREATE ROLE "{role}"'))
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE workspaces (id uuid PRIMARY KEY)"))
            conn.execute(
                text("INSERT INTO workspaces VALUES (:ws), (:other)"),
                {"ws": workspace_id, "other": other_workspace_id},
            )
            conn.execute(
                text("CREATE TABLE guard_knowledge_index (id uuid PRIMARY KEY)")
            )
            conn.execute(text("""CREATE TABLE guard_audit_events (
                id uuid PRIMARY KEY,
                workspace_id uuid NOT NULL REFERENCES workspaces(id),
                decision text NOT NULL
            )"""))
            conn.execute(text("ALTER TABLE guard_audit_events ENABLE ROW LEVEL SECURITY"))
            conn.execute(text("ALTER TABLE guard_audit_events FORCE ROW LEVEL SECURITY"))
            conn.execute(text("""CREATE POLICY guard_audit_events_workspace
                ON guard_audit_events
                USING (workspace_id = NULLIF(current_setting('app.current_workspace', true), '')::uuid)
                WITH CHECK (workspace_id = NULLIF(current_setting('app.current_workspace', true), '')::uuid)"""))
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
            conn.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"'))
            conn.execute(
                text(
                    f'GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA "{schema}" TO "{role}"'
                )
            )
        yield engine, role, workspace_id, other_workspace_id, migration
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
            conn.execute(text(f'DROP ROLE "{role}"'))
        admin.dispose()


def _insert_intent(conn, workspace_id, version="v1"):
    conn.execute(
        text("""INSERT INTO guard_projection_intents
        (workspace_id, source_kind, source_id, source_version, max_attempts)
        VALUES (:workspace_id, 'audit_event', 'event-1', :version, 5)"""),
        {"workspace_id": workspace_id, "version": version},
    )


def test_projection_migration_rls_constraints_and_safe_downgrade(projection_database):
    engine, role, workspace_id, other_workspace_id, migration = projection_database
    with engine.begin() as conn:
        conn.execute(text(f'SET LOCAL ROLE "{role}"'))
        assert (
            conn.execute(
                text("SELECT count(*) FROM guard_projection_intents")
            ).scalar_one()
            == 0
        )
        conn.execute(
            text("SELECT set_config('app.current_workspace', :ws, true)"),
            {"ws": str(workspace_id)},
        )
        _insert_intent(conn, workspace_id)
        assert (
            conn.execute(
                text("SELECT count(*) FROM guard_projection_intents")
            ).scalar_one()
            == 1
        )
        with pytest.raises(IntegrityError), conn.begin_nested():
            _insert_intent(conn, workspace_id)
        with pytest.raises((IntegrityError, ProgrammingError)), conn.begin_nested():
            _insert_intent(conn, other_workspace_id, version="v2")
        conn.execute(
            text("SELECT set_config('app.current_workspace', :ws, true)"),
            {"ws": str(other_workspace_id)},
        )
        assert conn.execute(
            text("SELECT count(*) FROM guard_projection_intents")
        ).scalar_one() == 0

    with (
        engine.begin() as conn,
        Operations.context(MigrationContext.configure(conn)),
        pytest.raises(RuntimeError, match="Export or drain guard_projection_intents"),
    ):
        migration.downgrade()


def test_atomic_source_and_projection_rollback_visibility(projection_database):
    engine, role, workspace_id, other_workspace_id, _migration = projection_database
    event_id = uuid4()
    source_id = str(event_id)

    with engine.connect() as conn:
        transaction = conn.begin()
        conn.execute(text(f'SET LOCAL ROLE "{role}"'))
        conn.execute(
            text("SELECT set_config('app.current_workspace', :ws, true)"),
            {"ws": str(workspace_id)},
        )
        conn.execute(
            text("INSERT INTO guard_audit_events (id, workspace_id, decision) VALUES (:id, :ws, 'blocked')"),
            {"id": event_id, "ws": workspace_id},
        )
        conn.execute(
            text("""INSERT INTO guard_projection_intents
                (workspace_id, source_kind, source_id, source_version, max_attempts)
                VALUES (:ws, 'audit_event', :source_id, 'v1', 5)"""),
            {"ws": workspace_id, "source_id": source_id},
        )
        assert conn.execute(text("SELECT count(*) FROM guard_audit_events")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM guard_projection_intents")).scalar_one() == 1
        transaction.rollback()

    with engine.begin() as conn:
        conn.execute(text(f'SET LOCAL ROLE "{role}"'))
        conn.execute(
            text("SELECT set_config('app.current_workspace', :ws, true)"),
            {"ws": str(workspace_id)},
        )
        assert conn.execute(text("SELECT count(*) FROM guard_audit_events")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM guard_projection_intents")).scalar_one() == 0

        conn.execute(
            text("SELECT set_config('app.current_workspace', :ws, true)"),
            {"ws": str(other_workspace_id)},
        )
        assert conn.execute(text("SELECT count(*) FROM guard_audit_events")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM guard_projection_intents")).scalar_one() == 0
