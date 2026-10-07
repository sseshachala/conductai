from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

# Importing the helpers installs the prometheus_client shim before any app import.
from tests.guard._projection_queue_helpers import (  # noqa: F401 — fixtures
    NOW,
    FakeDB,
    FakeStatement,
    _disable_rls_sql,
    make_intent,
    message_for,
    persist_reconciliation_intents,
    reconciliation_db,
)

from app.modules.guard import knowledge
from app.modules.guard import projection_intents
from app.modules.guard import projection_queue as pq
from app.modules.guard.projection_contract import (
    PROJECTION_QUEUE_KEY,
    ProjectionIntentStatus,
    ProjectionMessage,
    ProjectionSourceKind,
)


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
    monkeypatch.setattr(projection_intents, "insert", lambda model: statement)
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
    monkeypatch.setattr(projection_intents, "insert", lambda model: statement)
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


def test_redis_payload_is_projection_message_json_only():
    intent = make_intent()
    msg = message_for(intent)
    client = FakeRedis()
    assert pq.dispatch_projection_message(msg, redis_client=client) is True
    key, raw = client.pipe.pushed[0]
    assert key == PROJECTION_QUEUE_KEY
    assert ProjectionMessage.from_json(raw) == msg


def test_projection_redis_clients_bound_nonblocking_reads(monkeypatch):
    calls = []

    def from_url(url, **kwargs):
        calls.append((url, kwargs))
        return object()

    monkeypatch.setattr(pq.redis, 'from_url', from_url)
    monkeypatch.setattr(pq.settings, 'guard_projection_redis_connect_timeout_seconds', 0.1)
    monkeypatch.setattr(pq.settings, 'guard_projection_redis_socket_timeout_seconds', 0.2)

    pq.projection_redis_client()
    pq.projection_redis_client(blocking=True)

    assert calls[0][1]['socket_connect_timeout'] == 0.1
    assert calls[0][1]['socket_timeout'] == 0.2
    assert calls[0][1]['retry_on_timeout'] is False
    assert 'socket_timeout' not in calls[1][1]


def test_dispatch_timeouts_fail_open_without_swallowing_programming_errors(monkeypatch):
    intent = make_intent()
    msg = message_for(intent)

    class ConnectTimeoutRedis:
        def pipeline(self):
            raise pq.redis.TimeoutError('bounded connect timeout')

    class ReadTimeoutPipeline(FakePipeline):
        def execute(self):
            raise pq.redis.TimeoutError('bounded read timeout')

    class ReadTimeoutRedis:
        def __init__(self):
            self.pipe = ReadTimeoutPipeline()

        def pipeline(self):
            return self.pipe

    monkeypatch.setattr(pq, 'projection_redis_client', lambda: ConnectTimeoutRedis())
    assert pq.dispatch_projection_message(msg) is False
    assert pq.dispatch_projection_message(msg, redis_client=ReadTimeoutRedis()) is False

    class BrokenRedis:
        def pipeline(self):
            raise TypeError('programming defect')

    with pytest.raises(TypeError, match='programming defect'):
        pq.dispatch_projection_message(msg, redis_client=BrokenRedis())


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


def test_summary_provider_failure_supersedes_claim_when_successor_exists(monkeypatch):
    processing = make_intent(
        source_kind=ProjectionSourceKind.AUDIT_SUMMARY.value,
        source_id='summary-1',
        status=ProjectionIntentStatus.PROCESSING.value,
        attempts=1,
    )
    successor = make_intent(
        workspace_id=processing.workspace_id,
        source_kind=ProjectionSourceKind.AUDIT_SUMMARY.value,
        source_id=processing.source_id,
        source_version='2',
        status=ProjectionIntentStatus.PENDING.value,
    )
    db = FakeDB(intent=processing, successor=successor)
    claim = pq.ProjectionClaim(
        intent_id=processing.id,
        workspace_id=processing.workspace_id,
        attempts=1,
        max_attempts=processing.max_attempts,
    )

    outcome = pq._fail_projection_claim(
        lambda: db,
        claim,
        message_for(processing),
        RuntimeError('provider failed'),
        redis_client=None,
        now=NOW,
    )

    assert outcome == 'superseded'
    assert processing.status == ProjectionIntentStatus.SUPERSEDED.value
    assert processing.completed_at == NOW
    assert successor.status == ProjectionIntentStatus.PENDING.value


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
