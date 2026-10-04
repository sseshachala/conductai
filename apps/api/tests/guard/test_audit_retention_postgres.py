"""PR2 acceptance on PostgreSQL, including migration/RLS and storage races."""

import importlib.util
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.core.workspace_context import set_workspace_rls
from app.modules.guard.audit_archive import ArchiveIntegrityError, digest, read_verified_archive
from app.modules.guard.audit_retention import archive_workspace_once, checkpoint_anchor, verify_audit_history
from app.modules.guard.models import GuardAuditArchiveSegment, GuardAuditEvent, GuardAuditRetentionHold
from tests.guard.test_audit_archive import MemoryStore, archive_settings

NOW = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)


@pytest.fixture
def archive_database():
    if os.environ.get("AUDIT_RETENTION_REAL_TESTS") != "1":
        pytest.skip("Set AUDIT_RETENTION_REAL_TESTS=1 with a migrated disposable PostgreSQL database")
    import app.main  # Register all ORM relationships before querying models.
    schema, role = "audit_archive_" + uuid4().hex, "archive_role_" + uuid4().hex
    admin = create_engine(settings.sqlalchemy_database_url)
    engine = create_engine(settings.sqlalchemy_database_url, pool_size=1, max_overflow=0,
                           connect_args={"options": f"-csearch_path={schema},public"})
    workspace, other = uuid4(), uuid4()
    migration_path = Path(__file__).resolve().parents[2] / "alembic/versions/0166_guard_audit_archives.py"
    spec = importlib.util.spec_from_file_location("archive_migration", migration_path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with admin.begin() as conn:
        conn.execute(CreateSchema(schema))
        conn.execute(text(f'CREATE ROLE "{role}"'))
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE workspaces (id uuid PRIMARY KEY)"))
            conn.execute(text("INSERT INTO workspaces VALUES (:ws), (:other)"), {"ws": workspace, "other": other})
            conn.execute(text("CREATE TABLE guard_audit_events (LIKE public.guard_audit_events INCLUDING DEFAULTS)"))
            conn.execute(text("ALTER TABLE guard_audit_events DROP COLUMN IF EXISTS archive_segment_id"))
            conn.execute(text("ALTER TABLE guard_audit_events ADD PRIMARY KEY (id)"))
            conn.execute(text("CREATE TABLE budget_reservations (request_id uuid, workspace_id uuid, status text)"))
            conn.execute(text("CREATE TABLE llm_attempt_receipts (LIKE public.llm_attempt_receipts INCLUDING DEFAULTS)"))
            with Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
            conn.execute(text("ALTER TABLE guard_audit_events ENABLE ROW LEVEL SECURITY"))
            conn.execute(text("ALTER TABLE guard_audit_events FORCE ROW LEVEL SECURITY"))
            conn.execute(text("""CREATE POLICY audit_workspace ON guard_audit_events
                USING (workspace_id = NULLIF(current_setting('app.current_workspace', true), '')::uuid)
                WITH CHECK (workspace_id = NULLIF(current_setting('app.current_workspace', true), '')::uuid)"""))
            conn.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"'))
            conn.execute(text(f'GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA "{schema}" TO "{role}"'))
        factory = sessionmaker(bind=engine)
        yield engine, factory, workspace, other, role, migration
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
            conn.execute(text(f'DROP ROLE "{role}"'))
        admin.dispose()


def seed(factory, workspace, *, count=3, start=None, lifecycle=None, decision="allowed"):
    previous, ids = "", []
    with factory() as db:
        set_workspace_rls(db, workspace)
        for index in range(count):
            ts = (start or NOW - timedelta(days=31)) + timedelta(seconds=index)
            entry = digest(f"{ts.isoformat()}|bash|{decision}|{previous}".encode())
            row = GuardAuditEvent(id=uuid4(), workspace_id=workspace, ai_tool="claude_code", source="hook",
                tool_call="bash", decision=decision, ts=ts, previous_hash=previous, entry_hash=entry,
                input_summary="full raw payload " + "x" * 4000, result_summary="result " + "y" * 4000,
                blast_radius={"paths": ["/workspace/example"]}, cost_usd_after=1.25, tokens_after=100,
                lifecycle_state=lifecycle, routing_meta={"usage": {"input_tokens": 100}})
            db.add(row)
            ids.append(row.id)
            previous = entry
        db.commit()
    return ids


def test_archive_migration_rls_and_safe_downgrade(archive_database):
    engine, factory, workspace, other, role, migration = archive_database
    with engine.begin() as conn:
        conn.execute(text(f'SET LOCAL ROLE "{role}"'))
        assert conn.execute(text("SELECT count(*) FROM guard_audit_retention_holds")).scalar() == 0
        conn.execute(text("SELECT set_config('app.current_workspace', :ws, true)"), {"ws": str(workspace)})
        conn.execute(text("INSERT INTO guard_audit_retention_holds (id,workspace_id,starts_at,reason) VALUES (:id,:ws,:ts,'test')"),
                     {"id": uuid4(), "ws": workspace, "ts": NOW})
        conn.execute(text("SELECT set_config('app.current_workspace', :ws, true)"), {"ws": str(other)})
        assert conn.execute(text("SELECT count(*) FROM guard_audit_retention_holds")).scalar() == 0
    with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
        migration.downgrade()
        migration.upgrade()


def test_verified_prefix_keeps_receipts_spend_and_chain(archive_database, archive_settings):
    engine, factory, workspace, other, _, migration = archive_database
    ids = seed(factory, workspace)
    seed(factory, other)
    store = MemoryStore(on_write=lambda: assert_pool_released(engine))
    before = totals(factory, workspace)
    before_spend = spend(factory, workspace)
    first = archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, store=store, now=NOW)
    assert first["archived"] == 2
    assert totals(factory, workspace) == before
    assert spend(factory, workspace) == before_spend == {None: 3_750_000}
    with factory() as db:
        history = verify_audit_history(db, workspace, settings_obj=archive_settings)
        assert history["valid"] is True and history["total"] == 3
        for row in db.query(GuardAuditEvent).filter(GuardAuditEvent.id.in_(ids[:2])):
            assert row.input_summary is None and row.result_summary is None and row.blast_radius is None
            assert row.routing_meta == {"usage": {"input_tokens": 100}}
        assert db.get(GuardAuditEvent, ids[2]).input_summary
        assert db.query(GuardAuditEvent).filter(GuardAuditEvent.workspace_id == other, GuardAuditEvent.archive_segment_id.isnot(None)).count() == 0
        segment = db.query(GuardAuditArchiveSegment).filter(GuardAuditArchiveSegment.workspace_id == workspace).one()
        rows = read_verified_archive(segment.manifest, segment.signature, archive_settings, store, workspace_id=str(workspace))
        assert rows[0]["input_summary"].startswith("full raw payload")
    second = archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, store=store, now=NOW)
    assert second["archived"] == 1
    assert archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, store=store, now=NOW)["archived"] == 0
    with factory() as db:
        history = verify_audit_history(db, workspace, settings_obj=archive_settings)
        assert history["valid"] is True and history["total"] == 3
        assert history["verified_from"] == (NOW - timedelta(days=31)).isoformat()
        assert history["last_event"] == (NOW - timedelta(days=31) + timedelta(seconds=2)).isoformat()
    with pytest.raises(RuntimeError, match="Restore"):
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()


def assert_pool_released(engine):
    assert engine.pool.checkedout() == 0


def totals(factory, workspace):
    with factory() as db:
        return tuple(db.query(func.count(GuardAuditEvent.id), func.sum(GuardAuditEvent.cost_usd_after),
                              func.sum(GuardAuditEvent.tokens_after)).filter(GuardAuditEvent.workspace_id == workspace).one())


def spend(factory, workspace):
    from app.runtime.accounting.reader import AccountingReader
    with factory() as db:
        return AccountingReader(db).spend_micros_by_workspace(workspace_id=workspace, since=NOW - timedelta(days=32))


@pytest.mark.parametrize("mode", ["dry_run", "disabled", "unconfigured", "cutoff"])
def test_safe_defaults_and_cutoff_do_not_compact(archive_database, archive_settings, mode):
    _, factory, workspace, *_ = archive_database
    ids = seed(factory, workspace, start=NOW - timedelta(days=30) if mode == "cutoff" else None)
    if mode == "dry_run": archive_settings.guard_audit_retention_dry_run = True
    if mode == "disabled": archive_settings.guard_audit_retention_enabled = False
    if mode == "unconfigured": archive_settings.guard_audit_retention_days = None
    store = MemoryStore()
    result = archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, store=store, now=NOW)
    assert result["archived"] == 0 and not store.objects
    with factory() as db:
        assert all(db.get(GuardAuditEvent, value).input_summary for value in ids)


@pytest.mark.parametrize("blocker", ["hold", "accepted", "reservation"])
def test_held_or_unfinished_prefix_is_not_skipped(archive_database, archive_settings, blocker):
    _, factory, workspace, *_ = archive_database
    ids = seed(factory, workspace, lifecycle="accepted" if blocker == "accepted" else None)
    with factory() as db:
        if blocker == "hold":
            db.add(GuardAuditRetentionHold(workspace_id=workspace, starts_at=NOW - timedelta(days=32), reason="legal hold"))
        if blocker == "reservation":
            request = uuid4()
            db.get(GuardAuditEvent, ids[0]).request_id = request
            db.execute(text("INSERT INTO budget_reservations VALUES (:req,:ws,'open')"), {"req": request, "ws": workspace})
        db.commit()
    store = MemoryStore()
    result = archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, store=store, now=NOW)
    assert result["archived"] == 0 and not store.objects and result["blocked_reason"]


@pytest.mark.parametrize("race", ["hold", "update", "delete", "storage_failure"])
def test_storage_failure_or_source_race_causes_zero_compaction(archive_database, archive_settings, race):
    engine, factory, workspace, *_ = archive_database
    ids = seed(factory, workspace)
    fired = False
    def during_storage():
        nonlocal fired
        assert_pool_released(engine)
        if fired: return
        fired = True
        if race == "storage_failure": raise TimeoutError("storage down")
        with factory() as db:
            if race == "hold":
                db.add(GuardAuditRetentionHold(workspace_id=workspace, starts_at=NOW - timedelta(days=32), reason="new hold"))
            elif race == "update": db.get(GuardAuditEvent, ids[0]).result_summary = "changed"
            elif race == "delete": db.delete(db.get(GuardAuditEvent, ids[0]))
            db.commit()
    store = MemoryStore(on_write=during_storage)
    if race == "storage_failure":
        with pytest.raises(TimeoutError):
            archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, store=store, now=NOW)
    else:
        result = archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, store=store, now=NOW)
        assert result["archived"] == 0 and result["blocked_reason"]
    with factory() as db:
        assert db.query(GuardAuditArchiveSegment).count() == 0
        assert db.query(GuardAuditEvent).filter(GuardAuditEvent.archive_segment_id.isnot(None)).count() == 0


def test_tampered_checkpoint_or_retained_tail_fails(archive_database, archive_settings):
    _, factory, workspace, *_ = archive_database
    ids = seed(factory, workspace)
    archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, store=MemoryStore(), now=NOW)
    with factory() as db:
        row = db.get(GuardAuditEvent, ids[2])
        row.tool_call = "tampered"
        db.commit()
        assert verify_audit_history(db, workspace, settings_obj=archive_settings)["valid"] is False
        row.tool_call = "bash"
        segment = db.query(GuardAuditArchiveSegment).one()
        segment.signature = "0" * 64
        db.commit()
        assert verify_audit_history(db, workspace, settings_obj=archive_settings)["valid"] is False
        with pytest.raises(ArchiveIntegrityError):
            checkpoint_anchor(db, workspace, archive_settings)


def test_upload_interruption_is_idempotently_resumed(archive_database, archive_settings):
    _, factory, workspace, *_ = archive_database
    seed(factory, workspace)
    class InterruptedStore(MemoryStore):
        interrupt = True
        def read(self, key):
            if self.interrupt:
                raise TimeoutError("interrupted after upload")
            return super().read(key)
    store = InterruptedStore()
    with pytest.raises(TimeoutError):
        archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, store=store, now=NOW)
    assert len(store.objects) == 2
    assert totals(factory, workspace)[0] == 3
    store.interrupt = False
    assert archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, store=store, now=NOW)["archived"] == 2
    assert len(store.objects) == 2


def test_concurrent_archive_commit_stops_stale_compaction(archive_database, archive_settings):
    engine, factory, workspace, *_ = archive_database
    seed(factory, workspace)
    fired = False
    def concurrent_archive():
        nonlocal fired
        assert_pool_released(engine)
        if fired:
            return
        fired = True
        assert archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings,
                                      store=store, now=NOW)["archived"] == 2
    store = MemoryStore(on_write=concurrent_archive)
    result = archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, store=store, now=NOW)
    assert result["archived"] == 0 and result["blocked_reason"] == "checkpoint_changed"
    with factory() as db:
        assert db.query(GuardAuditArchiveSegment).count() == 1
        assert db.query(GuardAuditEvent).filter(GuardAuditEvent.archive_segment_id.isnot(None)).count() == 2


def test_hold_release_resumes_and_foreign_hold_is_not_released(archive_database, archive_settings):
    from fastapi import HTTPException
    from app.modules.guard.routers.audit_retention import HoldIn, create_hold, release_hold
    _, factory, workspace, other, *_ = archive_database
    seed(factory, workspace)
    with factory() as db:
        hold = create_hold(HoldIn(starts_at=NOW - timedelta(days=32), reason="test hold"), db, str(workspace))
        hold_id = hold.id
    assert archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, now=NOW)["blocked_reason"] == "legal_hold"
    with factory() as db, pytest.raises(HTTPException) as error:
        release_hold(hold_id, db, str(other))
    assert error.value.status_code == 404
    with factory() as db:
        assert release_hold(hold_id, db, str(workspace)) == {"released": True}
    assert archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings,
                                  store=MemoryStore(), now=NOW)["archived"] == 2


def test_archived_retrieval_scopes_workspace_and_releases_pool(archive_database, archive_settings, monkeypatch):
    from fastapi import HTTPException
    from app.modules.guard.routers import audit_retention as router
    engine, factory, workspace, other, *_ = archive_database
    ids = seed(factory, workspace)
    store = MemoryStore()
    archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, store=store, now=NOW)
    monkeypatch.setattr(router, "settings", archive_settings)
    monkeypatch.setattr(router, "S3ArchiveStore", lambda _settings: store)
    original_read = store.read
    def read(key):
        assert_pool_released(engine)
        return original_read(key)
    monkeypatch.setattr(store, "read", read)
    with factory() as db:
        result = router.archived_event(ids[0], db, str(workspace))
        assert result["input_summary"].startswith("full raw payload")
    with factory() as db, pytest.raises(HTTPException) as error:
        router.archived_event(ids[0], db, str(other))
    assert error.value.status_code == 404
    store.objects.clear()
    with factory() as db, pytest.raises(HTTPException) as error:
        router.archived_event(ids[0], db, str(workspace))
    assert error.value.status_code == 503


def test_receipt_identity_decision_and_rules_remain_online(archive_database, archive_settings):
    from app.modules.guard.routers.blocks import get_receipt
    _, factory, workspace, *_ = archive_database
    ids = seed(factory, workspace, decision="blocked")
    with factory() as db:
        before = get_receipt(ids[0], db, str(workspace))
    archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, store=MemoryStore(), now=NOW)
    with factory() as db:
        after = get_receipt(ids[0], db, str(workspace))
    assert after["input_summary"] is None
    assert {key: value for key, value in before.items() if key != "input_summary"} == {
        key: value for key, value in after.items() if key != "input_summary"}


def test_downgrade_cannot_hide_populated_archives_using_rls(archive_database, archive_settings):
    engine, factory, workspace, _, role, migration = archive_database
    seed(factory, workspace)
    archive_workspace_once(workspace, session_factory=factory, settings_obj=archive_settings, store=MemoryStore(), now=NOW)
    with pytest.raises(DBAPIError):
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            conn.execute(text(f'SET LOCAL ROLE "{role}"'))
            migration.downgrade()
