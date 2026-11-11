"""Tool-execution join view (#2169): record, resolve, and list by correlation id.

Runs on PostgreSQL in a throwaway schema (JSONB ``jsonb_exists`` + ON CONFLICT).
Skipped when no database is reachable.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import settings
from app.modules.guard.tool_executions import (
    executions_for_event,
    record_tool_execution,
    resolve_correlation_id,
    valid_correlation_id,
)

CID_A = "9c4f3e21a7b0d8e1"
CID_B = "1f8b3c22e5a06d94"
WS = uuid.uuid4()
OTHER_WS = uuid.uuid4()


@pytest.fixture
def db():
    import app.main  # noqa: F401 — register every mapper
    from app.models.guard_tool_execution import GuardToolExecution

    schema = "tool_exec_" + uuid.uuid4().hex
    admin = create_engine(settings.sqlalchemy_database_url)
    try:
        with admin.begin() as conn:
            conn.execute(CreateSchema(schema))
    except Exception:
        pytest.skip("PostgreSQL unavailable")
    engine = create_engine(settings.sqlalchemy_database_url,
                           connect_args={"options": f"-csearch_path={schema},public"})
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE workspaces (id uuid PRIMARY KEY)"))
            conn.execute(text("INSERT INTO workspaces VALUES (:a), (:b)"), {"a": WS, "b": OTHER_WS})
            conn.execute(text("CREATE TABLE guard_audit_events (LIKE public.guard_audit_events INCLUDING DEFAULTS)"))
            GuardToolExecution.__table__.create(conn)
        session = sessionmaker(bind=engine)()
        yield session
        session.close()
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def _gateway_row(db, mapping, ws=WS, source="gateway"):
    from app.modules.guard.models import GuardAuditEvent

    row = GuardAuditEvent(
        id=uuid.uuid4(), workspace_id=ws, ai_tool="gateway", source=source, decision="allowed",
        routing_meta={"tool_call_correlation_ids": mapping}, ts=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return row


def _record(db, **kw):
    args = dict(correlation_id=None, tool_use_id=None, tool_name="send_email", hook_session_id="s",
                clerk_user_id="u", execution_status="success", duration_ms=340)
    args.update(kw)
    ok = record_tool_execution(db, WS, **args)
    db.commit()
    return ok


def test_valid_correlation_id():
    assert valid_correlation_id(CID_A) == CID_A
    assert valid_correlation_id("nothex") is None
    assert valid_correlation_id(None) is None


def test_join_returns_reported_execution(db):
    row = _gateway_row(db, {"call_abc": CID_A, "call_def": CID_B})
    assert _record(db, correlation_id=CID_A)
    out = executions_for_event(db, row)
    assert [e["correlation_id"] for e in out["executions"]] == [CID_A]
    assert out["executions"][0]["tool_call_id"] == "call_abc"
    assert out["executions"][0]["tool_name"] == "send_email"
    assert out["executions"][0]["correlation_source"] == "reported"
    assert out["correlation_ids"] == {"call_abc": CID_A, "call_def": CID_B}


def test_empty_when_nothing_reported(db):
    row = _gateway_row(db, {"call_abc": CID_A})
    assert executions_for_event(db, row)["executions"] == []


def test_no_mapping_is_empty(db):
    row = _gateway_row(db, {})
    assert executions_for_event(db, row) == {"correlation_ids": {}, "executions": []}


def test_other_workspace_execution_is_not_joined(db):
    row = _gateway_row(db, {"call_abc": CID_A})
    assert record_tool_execution(db, OTHER_WS, correlation_id=CID_A, tool_use_id=None, tool_name="x",
                                 hook_session_id=None, clerk_user_id=None, execution_status="success",
                                 duration_ms=1)
    db.commit()
    assert executions_for_event(db, row)["executions"] == []


def test_resolves_correlation_from_tool_use_id(db):
    row = _gateway_row(db, {"toolu_123": CID_A})
    assert resolve_correlation_id(db, WS, "toolu_123") == CID_A
    assert resolve_correlation_id(db, OTHER_WS, "toolu_123") is None
    assert _record(db, tool_use_id="toolu_123")
    out = executions_for_event(db, row)
    assert out["executions"][0]["correlation_source"] == "resolved"


def test_unresolvable_is_not_recorded(db):
    assert not _record(db, tool_use_id="toolu_unknown")
    assert not _record(db, correlation_id="not-hex")


def test_upsert_updates_outcome(db):
    row = _gateway_row(db, {"call_abc": CID_A})
    _record(db, correlation_id=CID_A, execution_status="error", duration_ms=1)
    _record(db, correlation_id=CID_A, execution_status="success", duration_ms=2)
    out = executions_for_event(db, row)["executions"]
    assert len(out) == 1 and out[0]["execution_status"] == "success" and out[0]["duration_ms"] == 2
