from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app import worker
from app.core.config import Settings
from app.core.database import SessionLocal
from app.modules.guard import projection_queue, projection_retention
from app.modules.guard.observability.metrics import (
    GUARD_PROJECTION_OLDEST_AGE,
    GUARD_PROJECTION_QUEUE_DEPTH,
    GUARD_PROJECTION_RETENTION_INTENTS_EXPIRED,
    GUARD_PROJECTION_RETENTION_KNOWLEDGE_DELETED,
    GUARD_PROJECTION_RETENTION_RUNS,
)
from app.modules.guard.projection_contract import (
    PROJECTION_PROCESSING_KEY,
    PROJECTION_QUEUE_KEY,
)


class LoopStopped(Exception):
    pass


def test_retention_settings_are_safe_and_interval_is_bounded():
    configured = Settings()
    assert configured.guard_projection_retention_cleanup_enabled is False
    assert configured.guard_projection_retention_dry_run is True
    assert configured.guard_projection_retention_interval_seconds == 3600

    with pytest.raises(ValidationError):
        Settings(guard_projection_retention_interval_seconds=59)
    with pytest.raises(ValidationError):
        Settings(guard_projection_retention_interval_seconds=86401)


def test_retention_start_is_independent_and_safe_off(monkeypatch):
    monkeypatch.setattr(
        worker.settings, "guard_projection_retention_cleanup_enabled", False
    )
    assert worker._start_projection_retention() is None

    created = []

    class FakeThread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.started = False
            created.append(self)

        def start(self):
            self.started = True

    monkeypatch.setattr(
        worker.settings, "guard_projection_retention_cleanup_enabled", True
    )
    monkeypatch.setattr(worker.threading, "Thread", FakeThread)
    thread = worker._start_projection_retention()

    assert thread is created[0]
    assert thread.started is True
    assert thread.kwargs["daemon"] is True
    assert thread.kwargs["name"] == "projection-retention"
    assert thread.kwargs["target"] is worker._projection_retention_loop


def test_retention_loop_passes_factory_mode_and_aggregate_callback(monkeypatch):
    calls = []

    def run_once(**kwargs):
        calls.append(kwargs)
        kwargs["on_result"](
            {
                "dry_run": True,
                "knowledge_candidates": 2,
                "knowledge_deleted": 0,
                "intent_candidates": 1,
                "intents_expired": 0,
                "batches_committed": 0,
                "more_work": False,
            }
        )

    monkeypatch.setattr(projection_retention, "run_projection_retention_once", run_once)
    monkeypatch.setattr(worker.settings, "guard_projection_retention_dry_run", True)
    monkeypatch.setattr(
        worker.settings, "guard_projection_retention_interval_seconds", 60
    )
    monkeypatch.setattr(
        worker.time, "sleep", lambda _seconds: (_ for _ in ()).throw(LoopStopped())
    )

    with pytest.raises(LoopStopped):
        worker._projection_retention_loop()

    assert len(calls) == 1
    assert calls[0]["session_factory"] is SessionLocal
    assert calls[0]["dry_run"] is True
    assert calls[0]["on_result"] is worker._record_projection_retention_result


def test_retention_metrics_record_only_aggregate_changes():
    runs = GUARD_PROJECTION_RETENTION_RUNS.labels(
        outcome="success", dry_run="true", more_work="false"
    )
    knowledge = GUARD_PROJECTION_RETENTION_KNOWLEDGE_DELETED.labels(dry_run="true")
    intents = GUARD_PROJECTION_RETENTION_INTENTS_EXPIRED.labels(dry_run="true")
    before = (runs._value.get(), knowledge._value.get(), intents._value.get())

    worker._record_projection_retention_result(
        {
            "dry_run": True,
            "knowledge_candidates": 8,
            "knowledge_deleted": 3,
            "intent_candidates": 5,
            "intents_expired": 2,
            "batches_committed": 1,
            "more_work": False,
        }
    )

    assert runs._value.get() == before[0] + 1
    assert knowledge._value.get() == before[1] + 3
    assert intents._value.get() == before[2] + 2


def test_retention_loop_survives_cleanup_error(monkeypatch):
    attempts = []

    def fail_once(**_kwargs):
        attempts.append(1)
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(projection_retention, "run_projection_retention_once", fail_once)
    monkeypatch.setattr(worker.settings, "guard_projection_retention_dry_run", True)
    monkeypatch.setattr(
        worker.settings, "guard_projection_retention_interval_seconds", 60
    )
    monkeypatch.setattr(
        worker.time, "sleep", lambda _seconds: (_ for _ in ()).throw(LoopStopped())
    )
    errors = GUARD_PROJECTION_RETENTION_RUNS.labels(
        outcome="error", dry_run="true", more_work="unknown"
    )
    errors_before = errors._value.get()

    with pytest.raises(LoopStopped):
        worker._projection_retention_loop()
    assert attempts == [1]
    assert errors._value.get() == errors_before + 1


def test_reconciliation_refreshes_total_backlog_and_oldest_age(monkeypatch):
    class FakeRedis:
        def hgetall(self, _key):
            return {}

        def lrange(self, _key, _start, _end):
            return []

        def llen(self, key):
            return {
                PROJECTION_QUEUE_KEY: 4,
                PROJECTION_PROCESSING_KEY: 3,
            }[key]

    client = FakeRedis()

    def reconcile(*, redis_client):
        assert redis_client is client
        GUARD_PROJECTION_OLDEST_AGE.set(42)
        return 0

    monkeypatch.setattr(worker.redis, "from_url", lambda *_args, **_kwargs: client)
    monkeypatch.setattr(projection_queue, "reconcile_projection_intents", reconcile)
    monkeypatch.setattr(worker.settings, "guard_projection_paused", False)
    monkeypatch.setattr(
        worker.settings, "guard_projection_reconciliation_interval_seconds", 60
    )
    monkeypatch.setattr(
        worker.time, "sleep", lambda _seconds: (_ for _ in ()).throw(LoopStopped())
    )

    with pytest.raises(LoopStopped):
        worker._projection_reconciliation_loop()

    assert GUARD_PROJECTION_QUEUE_DEPTH._value.get() == 7
    assert GUARD_PROJECTION_OLDEST_AGE._value.get() == 42



def test_processing_recovery_handles_blmove_before_timestamp_without_leak(monkeypatch):
    raw = "message-1"

    class FakeRedis:
        def __init__(self):
            self.processing = [raw, raw]
            self.queue = []
            self.times = {"orphan": "1"}

        def hgetall(self, _key):
            return dict(self.times)

        def hset(self, _key, value, timestamp):
            self.times[value] = str(timestamp)

        def lrange(self, key, _start, _end):
            return list(self.processing if key == PROJECTION_PROCESSING_KEY else self.queue)

        def lrem(self, _key, _count, value):
            removed = self.processing.count(value)
            self.processing = [item for item in self.processing if item != value]
            return removed

        def hdel(self, _key, value):
            return int(self.times.pop(value, None) is not None)

        def lpos(self, _key, value):
            try:
                return self.queue.index(value)
            except ValueError:
                return None

        def llen(self, key):
            return len(self.processing if key == PROJECTION_PROCESSING_KEY else self.queue)

        def rpush(self, _key, value):
            self.queue.append(value)
            return len(self.queue)

    monkeypatch.setattr(worker.settings, "guard_projection_lease_seconds", 60)
    client = FakeRedis()

    adopted = worker._reconcile_projection_processing_entries(client, now=1000)

    assert adopted == 0
    assert client.processing == [raw, raw]
    assert client.times == {raw: "1000"}
    assert client.queue == []
    assert worker._projection_backlog_depth(client) == 2

    recovered = worker._reconcile_projection_processing_entries(client, now=1061)

    assert recovered == 1
    assert client.processing == []
    assert client.times == {}
    assert client.queue == [raw]
    assert worker._projection_backlog_depth(client) == 1

def test_deployment_defaults_use_safe_projection_rollout():
    root = Path(__file__).resolve().parents[4]
    render_source = (root / "render.yaml").read_text()
    helm_values = (root / "deploy/helm/conduct/values.yaml").read_text()

    assert "GUARD_PROJECTION_RETENTION_CLEANUP_ENABLED" in render_source
    assert "GUARD_PROJECTION_RETENTION_DRY_RUN" in render_source
    assert "config:\n  postgresUser" in helm_values
    assert "GUARD_PROJECTION_QUEUE_ENABLED: false" in helm_values
    assert "projection:" not in helm_values
