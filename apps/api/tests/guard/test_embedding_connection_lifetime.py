from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.modules.guard import embedding as embedding_module
from app.modules.guard import knowledge
from app.modules.guard.projection_contract import (
    ProjectionIntentStatus,
    ProjectionSourceKind,
)
from app.modules.guard.projection_policy import audit_event_source_version
from app.modules.guard.routers import knowledge_search, session_reports
from app.tools.registrations.lens import guard_core


class PoolState:
    checked_out = 0


class _IntentQuery:
    def __init__(self, intent):
        self.intent = intent

    def filter(self, *args):
        return self

    def first(self):
        return self.intent


class BlockingClient:
    dimensions = 1536

    def __init__(self, pool):
        self.pool = pool
        self.calls = 0

    def embed(self, text):
        assert self.pool.checked_out == 0
        self.calls += 1
        return [0.1, 0.2]


def test_detached_client_closes_credential_session_before_factory(monkeypatch):
    pool = PoolState()

    class FakeSession:
        def rollback(self):
            pool.checked_out = 0

        def close(self):
            pool.checked_out = 0

    def db_factory():
        pool.checked_out = 1
        return FakeSession()

    monkeypatch.setattr(embedding_module, "set_workspace_rls", lambda db, ws: None)
    monkeypatch.setattr(
        embedding_module,
        "get_credential",
        lambda db, ws, handle: {"OPENAI_API_KEY": "secret"},
    )

    client = BlockingClient(pool)

    def create_client(**kwargs):
        assert pool.checked_out == 0
        assert kwargs["openai_api_key"] == "secret"
        return client

    monkeypatch.setattr(embedding_module, "create_embedding_client", create_client)
    assert (
        embedding_module.embedding_client_for_workspace(
            str(uuid4()), db_factory=db_factory
        )
        is client
    )


def _event(ts=None, decision="blocked", input_summary="summary"):
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        ts=ts or datetime.now(timezone.utc),
        source="hook",
        ai_tool="codex",
        tool_call="bash",
        decision=decision,
        rule_id="rule-1",
        rule_message="blocked",
        entry_hash=uuid4().hex,
        input_summary=input_summary,
        evaluated_rules=[],
        user_email="dev@example.com",
    )


def _snapshot(event):
    canonical, metadata = knowledge._project_audit_event(event)
    return knowledge._ProjectionSnapshot(
        workspace_id=str(event.workspace_id),
        source_kind=ProjectionSourceKind.AUDIT_EVENT,
        source_id=str(event.id),
        source_version=audit_event_source_version(event),
        canonical_text=canonical,
        metadata=metadata,
        content_hash=knowledge._hash(canonical),
        source_timestamp=event.ts,
        expires_at=event.ts + timedelta(days=30),
    )


def test_projector_provider_wait_has_no_checked_out_connection(monkeypatch):
    pool = PoolState()
    event = _event()
    snapshot = _snapshot(event)
    client = BlockingClient(pool)

    def snapshot_phase(intent_id, workspace_id):
        pool.checked_out = 1
        pool.checked_out = 0
        return None, snapshot

    monkeypatch.setattr(knowledge, "_intent_snapshot", snapshot_phase)
    monkeypatch.setattr(knowledge, "_projection_is_current", lambda current: False)
    monkeypatch.setattr(knowledge, "embedding_client_for_workspace", lambda ws: client)

    def write_phase(current, vector, intent_id=None):
        assert pool.checked_out == 0
        pool.checked_out = 1
        pool.checked_out = 0
        return ProjectionIntentStatus.COMPLETED

    monkeypatch.setattr(knowledge, "_conditional_write", write_phase)
    assert (
        knowledge.process_projection_intent(str(uuid4()), str(event.workspace_id))
        is ProjectionIntentStatus.COMPLETED
    )
    assert client.calls == 1


def test_interactive_search_releases_request_session_before_provider(monkeypatch):
    pool = PoolState()
    pool.checked_out = 1
    client = BlockingClient(pool)

    class Result:
        def fetchall(self):
            return []

    class FakeDB:
        def rollback(self):
            pool.checked_out = 0

        def execute(self, statement, params):
            assert client.calls == 1
            assert params["projection_now"].tzinfo is timezone.utc
            assert "gki.workspace_id = CAST(:workspace_id AS uuid)" in str(statement)
            assert "gki.expires_at > :projection_now" in str(statement)
            pool.checked_out = 1
            return Result()

    monkeypatch.setattr(
        knowledge_search, "embedding_client_for_workspace", lambda ws: client
    )
    monkeypatch.setattr(knowledge_search, "set_workspace_rls", lambda db, ws: None)
    assert (
        knowledge_search.search_knowledge(
            q="query",
            kind=None,
            limit=5,
            _="member",
            workspace_id=str(uuid4()),
            db=FakeDB(),
        )
        == []
    )


def test_background_write_embeds_before_opening_write_session(monkeypatch):
    pool = PoolState()
    client = BlockingClient(pool)

    class Query:
        def filter(self, *args):
            return self

        def update(self, values, synchronize_session=False):
            assert client.calls == 1
            return 1

    class FakeDB:
        def __enter__(self):
            pool.checked_out = 1
            return self

        def __exit__(self, *args):
            pool.checked_out = 0

        def query(self, model):
            return Query()

        def commit(self):
            pool.checked_out = 0

    monkeypatch.setattr(
        session_reports, "_embedding_client_for_workspace", lambda ws: client
    )
    monkeypatch.setattr(session_reports, "SessionLocal", FakeDB)
    monkeypatch.setattr(session_reports, "set_workspace_rls", lambda db, ws: None)
    session_reports._embed_session_report(str(uuid4()), str(uuid4()), "report")
    assert client.calls == 1


def test_snapshot_rejects_stale_version_and_exact_expiry(monkeypatch):
    event = _event()
    stale, snapshot = knowledge._snapshot_source(
        event,
        workspace_id=str(event.workspace_id),
        source_kind=ProjectionSourceKind.AUDIT_EVENT,
        source_id=str(event.id),
        expected_version="older-version",
        now=event.ts,
    )
    assert stale is ProjectionIntentStatus.SUPERSEDED
    assert snapshot is None

    monkeypatch.setattr(knowledge.settings, "guard_projection_retention_days", 30)
    expired_event = _event(ts=datetime.now(timezone.utc) - timedelta(days=30))
    expired, snapshot = knowledge._snapshot_source(
        expired_event,
        workspace_id=str(expired_event.workspace_id),
        source_kind=ProjectionSourceKind.AUDIT_EVENT,
        source_id=str(expired_event.id),
        expected_version=audit_event_source_version(expired_event),
        now=expired_event.ts + timedelta(days=30),
    )
    assert expired is ProjectionIntentStatus.EXPIRED
    assert snapshot is None


def test_conditional_write_deletes_matching_projection_for_missing_source(monkeypatch):
    event = _event()
    snapshot = _snapshot(event)
    intent = SimpleNamespace(
        workspace_id=event.workspace_id,
        source_kind="audit_event",
        source_id=str(event.id),
        source_version=snapshot.source_version,
    )
    existing = SimpleNamespace(
        canonical_text=snapshot.canonical_text,
        content_hash=snapshot.content_hash,
        meta=snapshot.metadata,
        source_timestamp=snapshot.source_timestamp,
        expires_at=snapshot.expires_at,
    )

    class FakeDB:
        deleted = None
        commits = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query(self, model):
            return _IntentQuery(intent)

        def delete(self, row):
            self.deleted = row

        def commit(self):
            self.commits += 1

    db = FakeDB()
    monkeypatch.setattr(knowledge, "SessionLocal", lambda: db)
    monkeypatch.setattr(knowledge, "set_workspace_rls", lambda session, ws: None)
    monkeypatch.setattr(
        knowledge, "_locked_projection_for_snapshot", lambda *args: existing
    )
    monkeypatch.setattr(knowledge, "_newer_intent_exists", lambda *args: False)
    monkeypatch.setattr(knowledge, "_load_source", lambda *args, **kwargs: None)

    assert (
        knowledge._conditional_write(snapshot, [0.1], intent_id=str(uuid4()))
        is ProjectionIntentStatus.MISSING
    )
    assert db.deleted is existing
    assert db.commits == 1


def test_conditional_write_preserves_projection_when_newer_intent_exists(monkeypatch):
    event = _event()
    snapshot = _snapshot(event)
    intent = SimpleNamespace(
        workspace_id=event.workspace_id,
        source_kind="audit_event",
        source_id=str(event.id),
        source_version=snapshot.source_version,
    )
    existing = SimpleNamespace(
        canonical_text=snapshot.canonical_text,
        content_hash=snapshot.content_hash,
        meta=snapshot.metadata,
        source_timestamp=snapshot.source_timestamp,
        expires_at=snapshot.expires_at,
    )

    class FakeDB:
        deleted = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query(self, model):
            return _IntentQuery(intent)

        def delete(self, row):
            self.deleted = row

    db = FakeDB()
    monkeypatch.setattr(knowledge, "SessionLocal", lambda: db)
    monkeypatch.setattr(knowledge, "set_workspace_rls", lambda session, ws: None)
    monkeypatch.setattr(
        knowledge, "_locked_projection_for_snapshot", lambda *args: existing
    )
    monkeypatch.setattr(knowledge, "_newer_intent_exists", lambda *args: True)
    monkeypatch.setattr(knowledge, "_load_source", lambda *args, **kwargs: None)

    assert (
        knowledge._conditional_write(snapshot, [0.1], intent_id=str(uuid4()))
        is ProjectionIntentStatus.MISSING
    )
    assert db.deleted is None


def test_conditional_write_does_not_delete_newer_replacement(monkeypatch):
    event = _event()
    snapshot = _snapshot(event)
    replacement = _event(ts=event.ts, input_summary="new replacement")
    replacement.id = event.id
    replacement.workspace_id = event.workspace_id
    newer_projection = SimpleNamespace(
        canonical_text="newer projection",
        content_hash="newer-hash",
        meta={"version": "newer"},
        source_timestamp=event.ts,
        expires_at=snapshot.expires_at,
    )
    intent = SimpleNamespace(
        workspace_id=event.workspace_id,
        source_kind="audit_event",
        source_id=str(event.id),
        source_version=snapshot.source_version,
    )

    class FakeDB:
        deleted = None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query(self, model):
            return _IntentQuery(intent)

        def delete(self, row):
            self.deleted = row

    db = FakeDB()
    monkeypatch.setattr(knowledge, "SessionLocal", lambda: db)
    monkeypatch.setattr(knowledge, "set_workspace_rls", lambda session, ws: None)
    monkeypatch.setattr(
        knowledge, "_locked_projection_for_snapshot", lambda *args: newer_projection
    )
    monkeypatch.setattr(knowledge, "_load_source", lambda *args, **kwargs: replacement)

    assert (
        knowledge._conditional_write(snapshot, [0.1], intent_id=str(uuid4()))
        is ProjectionIntentStatus.SUPERSEDED
    )
    assert db.deleted is None


def test_conditional_write_rechecks_stale_version(monkeypatch):
    event = _event()
    snapshot = _snapshot(event)
    changed = _event(ts=event.ts, input_summary="changed")
    changed.id = event.id
    changed.workspace_id = event.workspace_id
    intent = SimpleNamespace(
        workspace_id=event.workspace_id,
        source_kind="audit_event",
        source_id=str(event.id),
        source_version=snapshot.source_version,
    )

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query(self, model):
            return _IntentQuery(intent)

    monkeypatch.setattr(knowledge, "SessionLocal", FakeDB)
    monkeypatch.setattr(knowledge, "set_workspace_rls", lambda db, ws: None)
    monkeypatch.setattr(
        knowledge, "_locked_projection_for_snapshot", lambda *args: None
    )
    monkeypatch.setattr(knowledge, "_load_source", lambda *args, **kwargs: changed)
    assert (
        knowledge._conditional_write(snapshot, [0.1], intent_id=str(uuid4()))
        is ProjectionIntentStatus.SUPERSEDED
    )


def test_conditional_write_rechecks_expiry(monkeypatch):
    event = _event(ts=datetime.now(timezone.utc) - timedelta(days=31))
    snapshot = _snapshot(event)
    snapshot = knowledge._ProjectionSnapshot(
        workspace_id=snapshot.workspace_id,
        source_kind=snapshot.source_kind,
        source_id=snapshot.source_id,
        source_version=snapshot.source_version,
        canonical_text=snapshot.canonical_text,
        metadata=snapshot.metadata,
        content_hash=snapshot.content_hash,
        source_timestamp=snapshot.source_timestamp,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    intent = SimpleNamespace(
        workspace_id=event.workspace_id,
        source_kind="audit_event",
        source_id=str(event.id),
        source_version=snapshot.source_version,
    )

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def query(self, model):
            return _IntentQuery(intent)

    monkeypatch.setattr(knowledge, "SessionLocal", FakeDB)
    monkeypatch.setattr(knowledge, "set_workspace_rls", lambda db, ws: None)
    monkeypatch.setattr(
        knowledge, "_locked_projection_for_snapshot", lambda *args: None
    )
    monkeypatch.setattr(knowledge, "_load_source", lambda *args, **kwargs: event)
    assert (
        knowledge._conditional_write(snapshot, [0.1], intent_id=str(uuid4()))
        is ProjectionIntentStatus.EXPIRED
    )


def test_lens_knowledge_search_uses_explicit_active_projection_cutoff(monkeypatch):
    pool = PoolState()
    client = BlockingClient(pool)

    class Result:
        def fetchall(self):
            return []

    class FakeDB:
        def execute(self, statement, params):
            assert client.calls == 1
            assert params["projection_now"].tzinfo is timezone.utc
            assert "gki.workspace_id = CAST(:workspace_id AS uuid)" in str(statement)
            assert "gki.expires_at > :projection_now" in str(statement)
            return Result()

        def close(self):
            pass

    monkeypatch.setattr(guard_core, "embedding_client_for_workspace", lambda ws: client)
    monkeypatch.setattr(guard_core, "set_workspace_rls", lambda db, ws: None)
    from app.core import database

    monkeypatch.setattr(database, "SessionLocal", FakeDB)

    ctx = SimpleNamespace(workspace_id=str(uuid4()))
    assert guard_core.search_knowledge(ctx, "query", limit=5) == []
