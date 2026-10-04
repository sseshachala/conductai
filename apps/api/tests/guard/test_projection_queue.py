from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

try:
    import prometheus_client  # noqa: F401
except ModuleNotFoundError:
    import sys
    import types

    class _Metric:
        def __init__(self, *args, **kwargs):
            pass

        def labels(self, **kwargs):
            return self

        def inc(self):
            pass

        def set(self, value):
            pass

    sys.modules["prometheus_client"] = types.SimpleNamespace(
        Counter=_Metric, Gauge=_Metric, Histogram=_Metric
    )

from app.modules.guard import knowledge
from app.modules.guard import projection_queue as pq
from app.modules.guard.models import GuardProjectionIntent
from app.modules.guard.observability.metrics import GUARD_PROJECTION_OLDEST_AGE
from app.modules.guard.projection_contract import (
    PROJECTION_QUEUE_KEY,
    ProjectionIntentStatus,
    ProjectionMessage,
    ProjectionSourceKind,
)

NOW = datetime(2026, 10, 3, 20, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _disable_rls_sql(monkeypatch):
    monkeypatch.setattr(pq, "set_workspace_rls", lambda db, workspace_id: None)


class FakeResult:
    def __init__(self, value):
        self.value = value

    def one(self):
        return self.value


class FakeStatement:
    def __init__(self):
        self.data = None

    def values(self, **values):
        self.data = values
        return self

    def on_conflict_do_update(self, **kwargs):
        return self

    def returning(self, *args):
        return self


class FakeQuery:
    def __init__(self, intent):
        self.intent = intent

    def filter(self, *args):
        return self

    def with_for_update(self, **kwargs):
        return self

    def first(self):
        return self.intent

    def order_by(self, *args):
        return self

    def limit(self, value):
        return self

    def all(self):
        return [self.intent] if self.intent is not None else []


class FakeDB:
    def __init__(self, *, intent=None, summary_id=None, versions=None):
        self.intent = intent
        self.summary_id = summary_id or uuid4()
        self.versions = iter(versions or [1])
        self.summary_intent_id = uuid4()
        self.intents = [intent] if intent is not None else []
        self.executed = []
        self.added = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)
        self.intent = value

    def flush(self):
        if self.added and self.added[-1].id is None:
            self.added[-1].id = uuid4()

    def execute(self, statement):
        data = dict(statement.data or {})
        self.executed.append(data)
        if "dimension_key" in data:
            return FakeResult((self.summary_id, next(self.versions)))
        if data.get("source_kind") == ProjectionSourceKind.AUDIT_SUMMARY.value:
            if self.intent is None or self.intent.status not in {"pending", "retry"}:
                self.intent = GuardProjectionIntent(id=uuid4(), **data)
                self.intents.append(self.intent)
            else:
                for key, value in data.items():
                    setattr(self.intent, key, value)
            return FakeResult(
                SimpleNamespace(
                    id=self.intent.id,
                    workspace_id=self.intent.workspace_id,
                    source_kind=self.intent.source_kind,
                    source_id=self.intent.source_id,
                    source_version=self.intent.source_version,
                )
            )
        return FakeResult((self.summary_id, next(self.versions)))

    def query(self, model):
        return FakeQuery(self.intent)

    def commit(self):
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def reconciliation_db(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE workspaces (id VARCHAR(32) PRIMARY KEY)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE guard_projection_intents ("
            "id VARCHAR(32) PRIMARY KEY, "
            "workspace_id VARCHAR(32) NOT NULL, "
            "source_kind VARCHAR(32) NOT NULL, "
            "source_id TEXT NOT NULL, "
            "source_version TEXT NOT NULL, "
            "status VARCHAR(20) NOT NULL, "
            "attempts INTEGER NOT NULL, "
            "max_attempts INTEGER NOT NULL, "
            "available_at DATETIME NOT NULL, "
            "expires_at DATETIME, "
            "lease_expires_at DATETIME, "
            "last_error VARCHAR(500), "
            "dispatched_at DATETIME, "
            "completed_at DATETIME, "
            "created_at DATETIME NOT NULL, "
            "updated_at DATETIME NOT NULL"
            ")"
        )
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(pq, "SessionLocal", factory)
    yield factory
    engine.dispose()


class ReconciliationRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)


def persist_reconciliation_intents(factory, workspace_id, intents):
    with factory() as db:
        db.execute(
            sa.text("INSERT INTO workspaces (id) VALUES (:id)"),
            {"id": workspace_id.hex},
        )
        db.add_all(intents)
        db.commit()


def event(decision="blocked", *, ts=NOW, rule_id="rule-1"):
    return SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        ts=ts,
        source="hook",
        ai_tool="codex",
        tool_call="bash",
        decision=decision,
        rule_id=rule_id,
        rule_message="policy",
        entry_hash=uuid4().hex,
        input_summary="secret prompt that must not be summarized",
    )


@pytest.mark.parametrize("decision", ["blocked", "warned", "approval"])
def test_security_outcomes_create_event_intents(decision):
    db = FakeDB()
    message = pq.persist_audit_event_projection(db, event(decision), now=NOW)
    assert message.source_kind is ProjectionSourceKind.AUDIT_EVENT
    assert db.added[-1].status == ProjectionIntentStatus.PENDING.value
    assert db.commits == 0


def test_high_severity_allowed_event_routes_individually():
    db = FakeDB()
    message = pq.persist_audit_event_projection(
        db,
        event("allowed"),
        evaluated_rules=[{"severity": "critical"}],
        now=NOW,
    )
    assert message.source_kind is ProjectionSourceKind.AUDIT_EVENT


def test_allowed_summary_coalesces_one_debounced_durable_intent(monkeypatch):
    statement = FakeStatement()
    monkeypatch.setattr(pq, "insert", lambda model: statement)
    summary_id = uuid4()
    db = FakeDB(summary_id=summary_id, versions=[1, 2])
    first = pq.persist_audit_event_projection(
        db, event("allowed", rule_id="person@example.com"), now=NOW
    )
    durable_id = db.intent.id
    second = pq.persist_audit_event_projection(
        db, event("allowed", rule_id="person@example.com"), now=NOW
    )

    assert first is second is None
    assert db.intent.id == durable_id
    assert db.intent.source_id == str(summary_id)
    assert db.intent.source_version == "2"
    assert db.intent.available_at == pq._summary_window(NOW)[1]
    assert db.intent.expires_at > db.intent.available_at
    summary_write = next(data for data in db.executed if "dimension_key" in data)
    assert summary_write["canonical_facts"]["rule_id"] != "person@example.com"
    assert "input_summary" not in summary_write["canonical_facts"]
    assert db.commits == 0


def test_allowed_summary_processing_race_creates_only_one_next_intent(monkeypatch):
    statement = FakeStatement()
    monkeypatch.setattr(pq, "insert", lambda model: statement)
    processing = make_intent(
        source_kind=ProjectionSourceKind.AUDIT_SUMMARY.value,
        source_id=str(uuid4()),
        source_version="1",
        status=ProjectionIntentStatus.PROCESSING.value,
    )
    db = FakeDB(intent=processing, summary_id=processing.source_id, versions=[2, 3])

    pq.persist_audit_event_projection(db, event("allowed"), now=NOW)
    next_intent = db.intent
    pq.persist_audit_event_projection(db, event("allowed"), now=NOW)

    assert db.intents == [processing, next_intent]
    assert processing.status == ProjectionIntentStatus.PROCESSING.value
    assert next_intent.status == ProjectionIntentStatus.PENDING.value
    assert next_intent.source_version == "3"
    assert next_intent.available_at == pq._summary_window(NOW)[1]


def test_intent_snapshot_workspace_mismatch_fails_closed(
    monkeypatch, reconciliation_db
):
    actual_workspace = uuid4()
    requested_workspace = uuid4()
    intent = make_intent(workspace_id=actual_workspace)
    persist_reconciliation_intents(reconciliation_db, actual_workspace, [intent])
    monkeypatch.setattr(knowledge, "SessionLocal", reconciliation_db)
    monkeypatch.setattr(knowledge, "set_workspace_rls", lambda db, ws: None)
    monkeypatch.setattr(
        knowledge,
        "_load_source",
        lambda *args, **kwargs: pytest.fail("mismatched workspace loaded source"),
    )

    status, snapshot = knowledge._intent_snapshot(
        str(intent.id), str(requested_workspace)
    )

    assert status is ProjectionIntentStatus.MISSING
    assert snapshot is None


def test_expired_event_is_rejected():
    db = FakeDB()
    expired = event("blocked", ts=NOW - timedelta(days=31))
    assert pq.persist_audit_event_projection(db, expired, now=NOW) is None
    assert db.added == []


class FakePipeline:
    def __init__(self, depth=0):
        self.depth = depth
        self.pushed = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def watch(self, *args):
        pass

    def llen(self, key):
        return self.depth

    def unwatch(self):
        pass

    def multi(self):
        pass

    def rpush(self, key, value):
        self.pushed.append((key, value))

    def execute(self):
        return [1]


class FakeRedis:
    def __init__(self, depth=0, fail=False):
        self.pipe = FakePipeline(depth)
        self.fail = fail

    def pipeline(self):
        if self.fail:
            raise ConnectionError("offline")
        return self.pipe

    def llen(self, key):
        return self.pipe.depth


def message_for(intent):
    return ProjectionMessage(
        intent_id=intent.id,
        workspace_id=intent.workspace_id,
        source_kind=intent.source_kind,
        source_id=intent.source_id,
        source_version=intent.source_version,
    )


def make_intent(**overrides):
    values = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "source_kind": "audit_event",
        "source_id": "source",
        "source_version": "v1",
        "status": "pending",
        "attempts": 0,
        "max_attempts": 2,
        "available_at": NOW,
        "lease_expires_at": None,
        "dispatched_at": None,
    }
    values.update(overrides)
    return GuardProjectionIntent(**values)


def test_redis_payload_is_projection_message_json_only():
    intent = make_intent()
    msg = message_for(intent)
    client = FakeRedis()
    assert pq.dispatch_projection_message(msg, redis_client=client) is True
    key, raw = client.pipe.pushed[0]
    assert key == PROJECTION_QUEUE_KEY
    assert ProjectionMessage.from_json(raw) == msg


def test_redis_unavailable_or_full_is_nonfatal(monkeypatch):
    intent = make_intent()
    msg = message_for(intent)
    assert (
        pq.dispatch_projection_message(msg, redis_client=FakeRedis(fail=True)) is False
    )
    monkeypatch.setattr(pq.settings, "guard_projection_queue_max_depth", 1)
    assert pq.dispatch_projection_message(msg, redis_client=FakeRedis(depth=1)) is False


def test_duplicate_message_does_not_steal_live_lease():
    intent = make_intent(
        status="processing", lease_expires_at=NOW + timedelta(seconds=30)
    )
    db = FakeDB(intent=intent)
    assert pq.claim_projection_intent(db, message_for(intent), now=NOW) is None
    assert intent.attempts == 0


def test_expired_lease_is_recovered():
    intent = make_intent(
        status="processing", lease_expires_at=NOW - timedelta(seconds=1)
    )
    db = FakeDB(intent=intent)
    claim = pq.claim_projection_intent(db, message_for(intent), now=NOW)
    assert claim == pq.ProjectionClaim(
        intent_id=intent.id,
        workspace_id=intent.workspace_id,
        attempts=1,
        max_attempts=intent.max_attempts,
    )
    assert intent.attempts == 1
    assert intent.lease_expires_at > NOW


def test_retry_then_dead_letter_uses_fresh_rls_transactions(monkeypatch):
    intent = make_intent()
    sessions = []
    rls_calls = []

    def db_factory():
        db = FakeDB(intent=intent)
        sessions.append(db)
        return db

    monkeypatch.setattr(
        knowledge,
        "process_projection_intent",
        lambda intent_id, workspace_id: (_ for _ in ()).throw(RuntimeError("secret prompt")),
        raising=False,
    )
    monkeypatch.setattr(pq, "set_workspace_rls", lambda db, ws: rls_calls.append((db, ws)))
    msg = message_for(intent)
    assert pq.process_projection_message(msg, db_factory=db_factory) == "retry"
    assert intent.last_error == "Projection processing failed (RuntimeError)"
    assert len(sessions) == 2
    assert rls_calls == [(sessions[0], intent.workspace_id), (sessions[1], intent.workspace_id)]

    intent.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert pq.process_projection_message(msg, db_factory=db_factory) == "dead_letter"
    assert intent.status == ProjectionIntentStatus.DEAD_LETTER.value
    assert len(sessions) == 4
    assert rls_calls[-2:] == [
        (sessions[2], intent.workspace_id),
        (sessions[3], intent.workspace_id),
    ]



def test_completion_uses_fresh_rls_transaction(monkeypatch):
    intent = make_intent()
    sessions = []
    rls_calls = []

    def db_factory():
        db = FakeDB(intent=intent)
        sessions.append(db)
        return db

    monkeypatch.setattr(
        knowledge,
        "process_projection_intent",
        lambda intent_id, workspace_id: ProjectionIntentStatus.COMPLETED.value,
        raising=False,
    )
    monkeypatch.setattr(pq, "set_workspace_rls", lambda db, ws: rls_calls.append((db, ws)))

    assert pq.process_projection_message(message_for(intent), db_factory=db_factory) == "completed"
    assert intent.status == ProjectionIntentStatus.COMPLETED.value
    assert len(sessions) == 2
    assert rls_calls == [(sessions[0], intent.workspace_id), (sessions[1], intent.workspace_id)]



def test_stale_claim_cannot_complete_newer_attempt():
    intent = make_intent(
        status=ProjectionIntentStatus.PROCESSING.value,
        attempts=2,
    )
    claim = pq.ProjectionClaim(
        intent_id=intent.id,
        workspace_id=intent.workspace_id,
        attempts=1,
        max_attempts=intent.max_attempts,
    )
    db = FakeDB(intent=intent)
    assert pq._complete_projection_claim(
        lambda: db,
        claim,
        ProjectionIntentStatus.COMPLETED,
        now=NOW,
    ) is False
    assert intent.status == ProjectionIntentStatus.PROCESSING.value
    assert db.commits == 0

def test_delivery_timeout_is_configurable_or_derived(monkeypatch):
    monkeypatch.setattr(pq.settings, "guard_projection_delivery_timeout_seconds", 17)
    assert pq._delivery_timeout_seconds() == 17
    monkeypatch.setattr(pq.settings, "guard_projection_delivery_timeout_seconds", None)
    monkeypatch.setattr(pq.settings, "guard_projection_lease_seconds", 90)
    monkeypatch.setattr(pq.settings, "guard_projection_reconciliation_interval_seconds", 60)
    assert pq._delivery_timeout_seconds() == 120


def test_reconciliation_reserves_stale_delivery_but_excludes_fresh_marker(
    reconciliation_db,
):
    workspace_id = uuid4()
    stale = make_intent(
        workspace_id=workspace_id,
        source_id="stale",
        dispatched_at=NOW - timedelta(seconds=121),
        created_at=NOW - timedelta(minutes=2),
        updated_at=NOW - timedelta(minutes=2),
    )
    fresh = make_intent(
        workspace_id=workspace_id,
        source_id="fresh",
        dispatched_at=NOW - timedelta(seconds=119),
        created_at=NOW - timedelta(minutes=1),
        updated_at=NOW - timedelta(minutes=1),
    )
    persist_reconciliation_intents(
        reconciliation_db,
        workspace_id,
        [stale, fresh],
    )

    messages, oldest = pq._reserve_reconciliation_messages(
        workspace_id,
        current=NOW,
        stale_before=NOW - timedelta(seconds=120),
        limit=10,
    )
    assert messages == [message_for(stale)]
    assert pq._utc(oldest) == stale.created_at
    with reconciliation_db() as db:
        stored = {
            intent.id: intent
            for intent in db.query(GuardProjectionIntent)
            .order_by(GuardProjectionIntent.created_at)
            .all()
        }
    assert pq._utc(stored[stale.id].dispatched_at) == NOW
    assert pq._utc(stored[fresh.id].dispatched_at) == NOW - timedelta(seconds=119)

    timeout = NOW + timedelta(seconds=1)
    messages, _ = pq._reserve_reconciliation_messages(
        workspace_id,
        current=timeout,
        stale_before=timeout - timedelta(seconds=120),
        limit=10,
    )
    assert messages == [message_for(fresh)]
    with reconciliation_db() as db:
        refreshed = db.get(GuardProjectionIntent, fresh.id)
    assert pq._utc(refreshed.dispatched_at) == timeout


def test_reconciliation_recovers_expired_processing(monkeypatch):
    expired = make_intent(
        status=ProjectionIntentStatus.PROCESSING.value,
        lease_expires_at=NOW - timedelta(seconds=1),
        dispatched_at=NOW - timedelta(minutes=10),
    )
    db = FakeDB(intent=expired)
    monkeypatch.setattr(pq, "SessionLocal", lambda: db)

    messages, _ = pq._reserve_reconciliation_messages(
        expired.workspace_id,
        current=NOW,
        stale_before=NOW - timedelta(seconds=120),
        limit=1,
    )
    assert messages == [message_for(expired)]
    assert expired.status == ProjectionIntentStatus.RETRY.value
    assert expired.available_at == NOW
    assert expired.lease_expires_at is None
    assert expired.dispatched_at == NOW


def test_failed_dispatch_retains_attempted_reservation_and_releases_later_ones(
    monkeypatch,
    reconciliation_db,
):
    workspace_id = uuid4()
    intents = [
        make_intent(
            workspace_id=workspace_id,
            source_id=f"source-{index}",
            created_at=NOW - timedelta(minutes=3 - index),
            updated_at=NOW - timedelta(minutes=3 - index),
        )
        for index in range(3)
    ]
    persist_reconciliation_intents(reconciliation_db, workspace_id, intents)
    attempted = []

    def fail_dispatch(message, *, redis_client):
        attempted.append(message.intent_id)
        return False

    monkeypatch.setattr(pq, "dispatch_projection_message", fail_dispatch)
    monkeypatch.setattr(
        pq.settings, "guard_projection_reconciliation_batch_size", 3
    )
    monkeypatch.setattr(
        pq.settings, "guard_projection_delivery_timeout_seconds", 120
    )

    assert (
        pq.reconcile_projection_intents(
            redis_client=ReconciliationRedis(),
            now=NOW,
        )
        == 0
    )
    assert attempted == [intents[0].id]
    assert GUARD_PROJECTION_OLDEST_AGE._value.get() == 180

    with reconciliation_db() as db:
        stored = {
            intent.id: intent
            for intent in db.query(GuardProjectionIntent)
            .order_by(GuardProjectionIntent.created_at)
            .all()
        }
    assert pq._utc(stored[intents[0].id].dispatched_at) == NOW
    assert stored[intents[1].id].dispatched_at is None
    assert stored[intents[2].id].dispatched_at is None

def test_reconciliation_query_has_stale_cutoff_lock_and_bound():
    source = Path(pq.__file__).read_text()
    assert "GuardProjectionIntent.dispatched_at <= stale_before" in source
    assert ".with_for_update(skip_locked=True)" in source
    assert ".limit(limit)" in source

def test_summary_partial_index_predicate_quotes_sql_literals():
    root = Path(__file__).resolve().parents[2]
    migration = (
        root / "alembic/versions/0165_guard_projection_intents.py"
    ).read_text()
    models = (root / "app/modules/guard/models.py").read_text()
    quote = chr(39)
    predicate = (
        f"source_kind = {quote}audit_summary{quote} "
        f"AND status IN ({quote}pending{quote}, {quote}retry{quote})"
    )

    assert predicate in migration
    assert predicate in models


def test_event_and_worker_wiring_preserve_queue_separation():
    root = Path(__file__).resolve().parents[2]
    events_source = (root / "app/modules/guard/routers/events.py").read_text()
    ingest_source = events_source[events_source.index("def ingest_event("):]
    worker_source = (root / "app/worker.py").read_text()
    rls_index = ingest_source.index("set_workspace_rls(db, ws_uuid)")
    persist_index = ingest_source.index("persist_audit_event_projection(")
    commit_index = ingest_source.index("db.commit()", persist_index)
    dispatch_index = ingest_source.index("dispatch_projection_message(projection_message")
    assert rls_index < persist_index < commit_index < dispatch_index
    assert (
        "not settings.guard_projection_paused and not settings.guard_projection_queue_enabled"
        in events_source
    )
    assert PROJECTION_QUEUE_KEY != "marshal:runs:queue"
    assert "PROJECTION_CONCURRENCY" in worker_source
    assert 'QUEUE_KEY              = "marshal:runs:queue"' in worker_source
