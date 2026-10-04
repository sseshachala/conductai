from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

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
        Counter=_Metric, Gauge=_Metric
    )

from app.modules.guard import knowledge
from app.modules.guard import projection_queue as pq
from app.modules.guard.models import GuardProjectionIntent
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


class FakeDB:
    def __init__(self, *, intent=None, summary_id=None, versions=None):
        self.intent = intent
        self.summary_id = summary_id or uuid4()
        self.versions = iter(versions or [1])
        self.added = []
        self.commits = 0

    def add(self, value):
        self.added.append(value)
        self.intent = value

    def flush(self):
        if self.added and self.added[-1].id is None:
            self.added[-1].id = uuid4()

    def execute(self, statement):
        return FakeResult((self.summary_id, next(self.versions)))

    def query(self, model):
        return FakeQuery(self.intent)

    def commit(self):
        self.commits += 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


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


def test_allowed_summary_is_stable_versioned_and_prompt_free(monkeypatch):
    statement = FakeStatement()
    monkeypatch.setattr(pq, "insert", lambda model: statement)
    summary_id = uuid4()
    db = FakeDB(summary_id=summary_id, versions=[1, 2])
    first = pq.persist_audit_event_projection(
        db, event("allowed", rule_id="person@example.com"), now=NOW
    )
    second = pq.persist_audit_event_projection(
        db, event("allowed", rule_id="person@example.com"), now=NOW
    )
    assert first.source_id == second.source_id == str(summary_id)
    assert (first.source_version, second.source_version) == ("1", "2")
    assert statement.data["canonical_facts"]["rule_id"] != "person@example.com"
    assert "input_summary" not in statement.data["canonical_facts"]
    assert db.commits == 0


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
    assert pq.claim_projection_intent(db, message_for(intent), now=NOW) is intent
    assert intent.attempts == 1
    assert intent.lease_expires_at > NOW


def test_retry_then_dead_letter(monkeypatch):
    intent = make_intent()
    db = FakeDB(intent=intent)
    monkeypatch.setattr(
        knowledge,
        "process_projection_intent",
        lambda intent_id: (_ for _ in ()).throw(RuntimeError("secret prompt")),
        raising=False,
    )
    monkeypatch.setattr(pq, "SessionLocal", lambda: db)
    msg = message_for(intent)
    assert pq.process_projection_message(msg, db_factory=lambda: db) == "retry"
    assert intent.last_error == "Projection processing failed (RuntimeError)"
    intent.available_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    assert pq.process_projection_message(msg, db_factory=lambda: db) == "dead_letter"
    assert intent.status == ProjectionIntentStatus.DEAD_LETTER.value


def test_event_and_worker_wiring_preserve_queue_separation():
    root = Path(__file__).resolve().parents[2]
    events_source = (root / "app/modules/guard/routers/events.py").read_text()
    worker_source = (root / "app/worker.py").read_text()
    assert events_source.index("db.commit()") < events_source.index(
        "dispatch_projection_message(projection_message"
    )
    assert (
        "not settings.guard_projection_paused and not settings.guard_projection_queue_enabled"
        in events_source
    )
    assert PROJECTION_QUEUE_KEY != "marshal:runs:queue"
    assert "PROJECTION_CONCURRENCY" in worker_source
    assert 'QUEUE_KEY              = "marshal:runs:queue"' in worker_source
