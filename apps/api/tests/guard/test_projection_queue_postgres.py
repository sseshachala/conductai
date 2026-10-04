"""Real PostgreSQL coverage for migration 0165 and tenant constraints."""

import importlib.util
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, ProgrammingError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import settings
from app.modules.guard import projection_queue as pq
from app.modules.guard.projection_contract import (
    ProjectionIntentStatus,
    ProjectionMessage,
    ProjectionSourceKind,
)


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
        / "alembic/versions/0165_guard_projection_intents.py"
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



def _insert_summary_pair(conn, workspace_id, *, now):
    source_id = str(uuid4())
    processing_id = uuid4()
    successor_id = uuid4()
    conn.execute(
        text("""INSERT INTO guard_projection_intents
        (id, workspace_id, source_kind, source_id, source_version, status,
         attempts, max_attempts, available_at, lease_expires_at, created_at, updated_at)
        VALUES
        (:processing_id, :ws, 'audit_summary', :source_id, '1', 'processing',
         1, 5, :available, :expired_lease, :processing_created, :processing_created),
        (:successor_id, :ws, 'audit_summary', :source_id, '2', 'pending',
         0, 5, :available, NULL, :successor_created, :successor_created)"""),
        {
            'processing_id': processing_id,
            'successor_id': successor_id,
            'ws': workspace_id,
            'source_id': source_id,
            'available': now - timedelta(minutes=1),
            'expired_lease': now - timedelta(seconds=1),
            'processing_created': now - timedelta(minutes=2),
            'successor_created': now - timedelta(minutes=1),
        },
    )
    return processing_id, successor_id, source_id


def test_summary_provider_failure_supersedes_old_claim_postgres(projection_database):
    engine, _role, workspace_id, _other_workspace_id, _migration = projection_database
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        processing_id, successor_id, source_id = _insert_summary_pair(
            conn, workspace_id, now=now
        )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    claim = pq.ProjectionClaim(
        intent_id=processing_id,
        workspace_id=workspace_id,
        attempts=1,
        max_attempts=5,
    )
    message = ProjectionMessage(
        intent_id=processing_id,
        workspace_id=workspace_id,
        source_kind=ProjectionSourceKind.AUDIT_SUMMARY,
        source_id=source_id,
        source_version='1',
    )

    outcome = pq._fail_projection_claim(
        factory,
        claim,
        message,
        RuntimeError('provider failed'),
        redis_client=None,
        now=now,
    )

    assert outcome == 'superseded'
    with engine.begin() as conn:
        rows = dict(
            conn.execute(
                text('SELECT id, status FROM guard_projection_intents WHERE id IN (:old, :new)'),
                {'old': processing_id, 'new': successor_id},
            ).all()
        )
    assert rows[processing_id] == ProjectionIntentStatus.SUPERSEDED.value
    assert rows[successor_id] == ProjectionIntentStatus.PENDING.value


def test_summary_expired_lease_supersedes_old_claim_postgres(
    projection_database, monkeypatch
):
    engine, _role, workspace_id, _other_workspace_id, _migration = projection_database
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        processing_id, successor_id, _source_id = _insert_summary_pair(
            conn, workspace_id, now=now
        )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(pq, 'SessionLocal', factory)

    messages, _oldest = pq._reserve_reconciliation_messages(
        workspace_id,
        current=now,
        stale_before=now - timedelta(minutes=5),
        limit=10,
    )

    assert [message.intent_id for message in messages] == [successor_id]
    with engine.begin() as conn:
        rows = dict(
            conn.execute(
                text('SELECT id, status FROM guard_projection_intents WHERE id IN (:old, :new)'),
                {'old': processing_id, 'new': successor_id},
            ).all()
        )
    assert rows[processing_id] == ProjectionIntentStatus.SUPERSEDED.value
    assert rows[successor_id] == ProjectionIntentStatus.PENDING.value
