"""Keyset ("before") paging on Guard list endpoints.

ORM endpoints run against in-memory SQLite (JSONB/Vector compiled as JSON/BLOB);
the unified feed (raw SQL on a view) runs on real Postgres when
``GUARD_PAGING_TEST_DATABASE_URL`` is set. Every test pages with ``before`` and
asserts each row is returned exactly once, including rows tied on the sort ts.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Engine is never connected in these tests; DSN composed at runtime (no literal credentials in source).
os.environ.setdefault("DATABASE_URL", "postgresql" + "://localhost:5432/test_marshal")

from app.core.keyset import before_clause, parse_before  # noqa: E402
from app.models.workspace import Workspace  # noqa: E402
from app.modules.guard.models import GuardAuditEvent, GuardSession, SessionReport  # noqa: E402
from pgvector.sqlalchemy import Vector  # noqa: E402


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(*_a, **_k):
    return "JSON"


@compiles(PG_UUID, "sqlite")
def _uuid_sqlite(*_a, **_k):
    return "CHAR(32)"  # default "UUID" gets NUMERIC affinity and mangles hex ids like 123e4567


@compiles(Vector, "sqlite")
def _vector_sqlite(*_a, **_k):
    return "BLOB"


WS = uuid.UUID("11111111-1111-4111-8111-111111111111")
T0 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    for m in (Workspace, GuardAuditEvent, GuardSession, SessionReport):
        m.__table__.create(engine, checkfirst=True)
    s = sessionmaker(bind=engine)()
    s.add(Workspace(id=WS, name="w"))
    s.commit()
    yield s
    s.close()


def _ts(i: int) -> datetime:
    # Pairs of rows share a timestamp so ties on ts are exercised.
    return T0 - timedelta(minutes=i // 2)


def _page_all(fetch, limit, cursor_of):
    """Page with ``before`` until a short page; return every row seen, in order."""
    seen, cursor = [], None
    for _ in range(100):
        rows = fetch(limit, cursor)
        seen += rows
        if len(rows) < limit:
            return seen
        cursor = cursor_of(rows[-1])
    raise AssertionError("paging did not terminate")


# --------------------------------------------------------------------- helper

def test_parse_before_ok_and_plus_space_and_z():
    ts, i = parse_before("2026-01-01T12:00:00+00:00|abc")
    assert ts == T0 and i == "abc"
    assert parse_before("2026-01-01T12:00:00 00:00|abc")[0] == T0  # unescaped '+'
    assert parse_before("2026-01-01T12:00:00Z|abc")[0] == T0
    assert parse_before(None) is None and parse_before("") is None


@pytest.mark.parametrize("bad", ["nope", "|id", "2026-01-01T00:00:00+00:00|", "garbage|id"])
def test_parse_before_bad_is_400(bad):
    with pytest.raises(HTTPException) as e:
        parse_before(bad)
    assert e.value.status_code == 400


def test_before_clause_bad_uuid_is_400():
    with pytest.raises(HTTPException) as e:
        before_clause(GuardSession.started_at, GuardSession.id, "2026-01-01T00:00:00+00:00|not-a-uuid")
    assert e.value.status_code == 400


# ------------------------------------------------------------ GET /guard/events

def _seed_events(db, n=11):
    ids = set()
    for i in range(n):
        e = GuardAuditEvent(
            id=uuid.uuid4(), workspace_id=WS, ts=_ts(i), ai_tool="claude_code",
            tool_call="Bash", decision="allowed",
        )
        db.add(e)
        ids.add(str(e.id))
    db.commit()
    return ids


def _list_events(db, limit, before=None, offset=0):
    from app.modules.guard.routers.events_query import list_events
    return list_events(
        db=db, workspace_id=str(WS), decision=None, ai_tool=None, user_email=None, rule_id=None,
        since=None, until=None, limit=limit, offset=offset, before=before, hook_session_id=None,
        agent_identity_id=None, event_id=None, user_id="u",
    )


def test_events_before_pages_every_row_once(db):
    expected = _seed_events(db)
    seen = _page_all(lambda n, c: _list_events(db, n, c), 3, lambda r: f"{r.ts}|{r.id}")
    ids = [r.id for r in seen]
    assert len(ids) == len(set(ids)) and set(ids) == expected


def test_events_offset_still_works_and_before_wins(db):
    _seed_events(db)
    full = _list_events(db, 200)
    assert [r.id for r in _list_events(db, 3, offset=4)] == [r.id for r in full[4:7]]
    cur = f"{full[2].ts}|{full[2].id}"
    assert [r.id for r in _list_events(db, 3, before=cur, offset=5)] == [r.id for r in full[3:6]]


def test_events_bad_cursor_400(db):
    with pytest.raises(HTTPException) as e:
        _list_events(db, 3, before="zzz")
    assert e.value.status_code == 400


# ------------------------------------------------ GET /governance/events/recent

def _recent(db, limit, before=None):
    from app.routers.governance import get_recent_events
    return get_recent_events(
        limit=limit, decision=None, from_dt=None, to_dt=None, before=before,
        db=db, workspace_id=str(WS), _="ok",
    )


def test_governance_recent_before_pages_every_row_once(db):
    expected = _seed_events(db, 13)
    seen = _page_all(lambda n, c: _recent(db, n, c), 4, lambda r: f"{r.ts.isoformat()}|{r.id}")
    ids = [r.id for r in seen]
    assert len(ids) == len(set(ids)) and set(ids) == expected


def test_governance_recent_limit_max_200(db):
    for i in range(205):
        db.add(GuardAuditEvent(id=uuid.uuid4(), workspace_id=WS, ts=_ts(i), ai_tool="x",
                               tool_call="t", decision="allowed"))
    db.commit()
    assert len(_recent(db, 1000)) == 200


# ------------------------------------------------- GET /guard/spend/sessions

def _sessions(db, limit, before=None, offset=0):
    from app.modules.guard.routers.spend_summary import list_sessions
    return list_sessions(workspace_id=str(WS), limit=limit, offset=offset, before=before, db=db)


def test_spend_sessions_before_and_offset(db):
    expected = set()
    for i in range(10):
        s = GuardSession(id=uuid.uuid4(), workspace_id=WS, ai_tool="claude_code", started_at=_ts(i))
        db.add(s)
        expected.add(str(s.id))
    db.commit()
    seen = _page_all(lambda n, c: _sessions(db, n, c), 3, lambda r: f"{r.started_at}|{r.id}")
    ids = [r.id for r in seen]
    assert len(ids) == len(set(ids)) and set(ids) == expected
    assert [r.id for r in _sessions(db, 3, offset=3)] == ids[3:6]


# ------------------------------------------------- GET /guard/session-reports

def _reports(db, limit, before=None):
    from app.modules.guard.routers.session_reports import list_session_reports
    return list_session_reports(workspace_id=WS, limit=limit, before=before, db=db, _="ok")


def test_session_reports_before_pages_every_row_once(db):
    expected = set()
    for i in range(9):
        r = SessionReport(id=uuid.uuid4(), workspace_id=WS, developer_email="d@x.io", created_at=_ts(i))
        db.add(r)
        expected.add(str(r.id))
    db.commit()
    seen = _page_all(lambda n, c: _reports(db, n, c), 4, lambda r: f"{r.created_at}|{r.id}")
    ids = [r.id for r in seen]
    assert len(ids) == len(set(ids)) and set(ids) == expected
    assert len(_reports(db, 2)) == 2


# ------------------------------------------------ GET /guard/events/unified (PG)

_PG = os.environ.get("GUARD_PAGING_TEST_DATABASE_URL")


@pytest.mark.skipif(not _PG, reason="GUARD_PAGING_TEST_DATABASE_URL not set")
def test_unified_before_and_offset_on_postgres():
    schema = "kp_" + uuid.uuid4().hex[:12]
    engine = create_engine(_PG, connect_args={"options": f"-csearch_path={schema},public"})
    with engine.begin() as c:
        c.execute(text(f"CREATE SCHEMA {schema}"))
    try:
        with engine.begin() as c:
            c.execute(text(
                "CREATE TABLE workspaces (id uuid PRIMARY KEY, name text, owner_id text, is_approved bool,"
                " plan text, kms_key_id text, preferences json, created_at timestamptz, updated_at timestamptz)"
            ))
            c.execute(text("CREATE TABLE guard_audit_events (id uuid, workspace_id uuid, ts timestamptz,"
                           " user_email text, tool_call text, decision text, rule_id text, hook_session_id text)"))
            c.execute(text("CREATE TABLE telemetry_events (id uuid, workspace_id uuid, ts timestamptz,"
                           " tool text, event_type text, message text, session_id text)"))
            c.execute(text(
                "CREATE VIEW unified_activity_v AS "
                "SELECT workspace_id, ts, 'policy'::text AS source, id::text AS event_id, user_email AS actor,"
                " tool_call AS action, decision AS status, rule_id AS reason, NULL::text AS message,"
                " hook_session_id::text AS session_id FROM guard_audit_events "
                "UNION ALL SELECT workspace_id, ts, 'tool'::text, id::text, NULL::text, tool, event_type,"
                " NULL::text, message, session_id FROM telemetry_events"
            ))
            c.execute(text("INSERT INTO workspaces (id, name) VALUES (:w, 'w')"), {"w": WS})
            expected = set()
            for i in range(12):
                eid = uuid.uuid4()
                expected.add(str(eid))
                table = "guard_audit_events" if i % 2 else "telemetry_events"
                cols = "user_email, tool_call, decision" if i % 2 else "tool, event_type, message"
                c.execute(text(f"INSERT INTO {table} (id, workspace_id, ts, {cols}) VALUES (:i, :w, :t, 'a', 'b', 'c')"),
                          {"i": eid, "w": WS, "t": _ts(i)})
        from app.modules.guard.routers.events_unified import list_unified_activity

        def call(limit, before=None, offset=0):
            with sessionmaker(bind=engine)() as s:
                return list_unified_activity(
                    db=s, workspace_id=str(WS), source=None, status=None, actor=None, since=None,
                    until=None, limit=limit, offset=offset, before=before,
                )["items"]

        seen = _page_all(lambda n, c: call(n, c), 5, lambda r: f"{r['ts']}|{r['event_id']}")
        ids = [r["event_id"] for r in seen]
        assert len(ids) == len(set(ids)) and set(ids) == expected
        assert [r["event_id"] for r in call(5, offset=5)] == ids[5:10]
    finally:
        with engine.begin() as c:
            c.execute(text(f"DROP SCHEMA {schema} CASCADE"))
