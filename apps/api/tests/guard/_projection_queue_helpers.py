"""Shared fakes, fixtures and builders for the Guard projection-queue tests
(``test_projection_queue.py``, ``test_projection_queue_reconciliation.py``).

Importing this module installs the ``prometheus_client`` shim (when the
package is missing) before any ``app.*`` import.
"""
from datetime import datetime, timezone
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

from app.modules.guard import projection_queue as pq
from app.modules.guard.models import GuardProjectionIntent
from app.modules.guard.projection_contract import (
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
    def __init__(self, *, intent=None, successor=None, summary_id=None, versions=None):
        self.intent = intent
        self.successor = successor
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
        if model is GuardProjectionIntent.id:
            return FakeQuery(self.successor)
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


def persist_reconciliation_intents(factory, workspace_id, intents):
    with factory() as db:
        db.execute(
            sa.text("INSERT INTO workspaces (id) VALUES (:id)"),
            {"id": workspace_id.hex},
        )
        db.add_all(intents)
        db.commit()


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
