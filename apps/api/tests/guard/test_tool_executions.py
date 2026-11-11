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
            conn.execute(text("CREATE TABLE workspace_users (workspace_id uuid, clerk_user_id text)"))
            conn.execute(text("CREATE TABLE agent_identities (LIKE public.agent_identities INCLUDING DEFAULTS)"))
            conn.execute(text("INSERT INTO workspace_users VALUES (:w, 'alice'), (:w, 'bob'), (:w, 'admin')"), {"w": WS})
            GuardToolExecution.__table__.create(conn)
        session = sessionmaker(bind=engine)()
        yield session
        session.close()
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def _gateway_row(db, mapping, ws=WS, source="gateway", user=None):
    from app.modules.guard.models import GuardAuditEvent

    row = GuardAuditEvent(
        id=uuid.uuid4(), workspace_id=ws, ai_tool="gateway", source=source, decision="allowed", clerk_user_id=user,
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


# ── Endpoint auth / scoping ──────────────────────────────────────────────────

def _route():
    from app.modules.guard.routers.events_query import router
    return next(r for r in router.routes if getattr(r, "path", "") == "/guard/events/{event_id}/tool-executions")


def test_endpoint_declares_permission_and_identity_dependencies():
    deps = [d.call for d in _route().dependant.dependencies]
    perms = [getattr(c, "__conduct_permission__", None) for c in deps]
    assert "guard.activity.view_own" in perms
    from app.core.auth import get_user_id, get_workspace_id
    assert get_user_id in deps and get_workspace_id in deps


@pytest.fixture
def perms(monkeypatch):
    """view_all only for 'admin'; view_own for every workspace member."""
    from fastapi import HTTPException
    from app.modules.guard import event_access

    def fake(*, user_id, workspace_id, credentials, db, permission):
        if permission.endswith("view_all") and user_id != "admin":
            raise HTTPException(status_code=403, detail="denied")
        return "role"
    monkeypatch.setattr(event_access, "check_permission", fake)


def _call(db, row, user):
    from app.modules.guard.routers.events_query import event_tool_executions
    return event_tool_executions(row.id, workspace_id=str(WS), user_id=user, _permission="x", db=db)


def test_endpoint_owner_sees_executions_and_others_get_404(db, perms):
    from fastapi import HTTPException
    row = _gateway_row(db, {"call_abc": CID_A}, user="alice")
    _record(db, correlation_id=CID_A)
    assert [e["correlation_id"] for e in _call(db, row, "alice")["executions"]] == [CID_A]
    assert len(_call(db, row, "admin")["executions"]) == 1  # view_all
    with pytest.raises(HTTPException) as exc:
        _call(db, row, "bob")  # member without view_all, not the owner
    assert exc.value.status_code == 404


def test_endpoint_non_member_is_forbidden(db, perms):
    from fastapi import HTTPException
    row = _gateway_row(db, {"call_abc": CID_A}, user="alice")
    with pytest.raises(HTTPException) as exc:
        _call(db, row, "outsider")
    assert exc.value.status_code == 403


def test_endpoint_event_in_other_workspace_is_404(db, perms):
    from fastapi import HTTPException
    row = _gateway_row(db, {"call_abc": CID_A}, ws=OTHER_WS, user="alice")
    with pytest.raises(HTTPException) as exc:
        _call(db, row, "admin")
    assert exc.value.status_code == 404
