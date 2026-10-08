"""Guard projection-queue reconciliation tests: stale delivery reservation,
expired processing recovery, summary supersession, query shape and wiring.

Split from ``test_projection_queue.py``; shared fakes and fixtures live in
``_projection_queue_helpers.py``.
"""
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

# Importing the helpers installs the prometheus_client shim before any app import.
from tests.guard._projection_queue_helpers import (  # noqa: F401 — fixtures
    NOW,
    FakeDB,
    _disable_rls_sql,
    make_intent,
    message_for,
    persist_reconciliation_intents,
    reconciliation_db,
)

from app.modules.guard import projection_queue as pq
from app.modules.guard.models import GuardProjectionIntent
from app.modules.guard.observability.metrics import GUARD_PROJECTION_OLDEST_AGE
from app.modules.guard.projection_contract import (
    PROJECTION_QUEUE_KEY,
    ProjectionIntentStatus,
    ProjectionSourceKind,
)


class ReconciliationRedis:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)

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


def test_reconciliation_supersedes_expired_summary_with_successor(monkeypatch):
    expired = make_intent(
        source_kind=ProjectionSourceKind.AUDIT_SUMMARY.value,
        source_id='summary-1',
        status=ProjectionIntentStatus.PROCESSING.value,
        lease_expires_at=NOW - timedelta(seconds=1),
        dispatched_at=NOW - timedelta(minutes=10),
    )
    successor = make_intent(
        workspace_id=expired.workspace_id,
        source_kind=ProjectionSourceKind.AUDIT_SUMMARY.value,
        source_id=expired.source_id,
        source_version='2',
        status=ProjectionIntentStatus.PENDING.value,
    )
    db = FakeDB(intent=expired, successor=successor)
    monkeypatch.setattr(pq, 'SessionLocal', lambda: db)

    messages, _ = pq._reserve_reconciliation_messages(
        expired.workspace_id,
        current=NOW,
        stale_before=NOW - timedelta(seconds=120),
        limit=1,
    )

    assert messages == []
    assert expired.status == ProjectionIntentStatus.SUPERSEDED.value
    assert expired.completed_at == NOW
    assert successor.status == ProjectionIntentStatus.PENDING.value


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
    models = (root / "app/modules/guard/models/projection.py").read_text()
    quote = chr(39)
    predicate = (
        f"source_kind = {quote}audit_summary{quote} "
        f"AND status IN ({quote}pending{quote}, {quote}retry{quote})"
    )

    assert predicate in migration
    assert predicate in models


def test_event_and_worker_wiring_preserve_queue_separation():
    root = Path(__file__).resolve().parents[2]
    events_source = (root / "app/modules/guard/routers/events_ingest.py").read_text()
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
