"""#2385 — audit export endpoint (GET /guard/events/export), SQLite-backed so the
real query/ordering/streaming code runs; chain hashes come from the real
``chain_hash_for_insert``."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.auth import get_user_id, get_workspace_id
from app.core.database import get_db
from app.main import app
from app.modules.guard import audit_export as ax
from app.modules.guard.models import GuardAuditEvent, chain_hash_for_insert

FIXTURE = (Path(__file__).resolve().parents[3] / "packages" / "conduct-cli" / "tests"
           / "fixtures" / "audit_export_chain.ndjson")
WS = str(uuid.UUID(int=1))
OTHER_WS = str(uuid.UUID(int=2))
T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


@compiles(JSONB, "sqlite")
def _jsonb_sqlite(*_a, **_k):
    return "JSON"


def _chain_rows(ws: str, specs, start=T0):
    """Build transient ORM rows chained with the real hash function."""
    prev_hash = {"v": None}

    class _Q:  # stands in for the db.query(...) chain chain_hash_for_insert uses
        def __getattr__(self, _n):
            return lambda *a, **k: self

        def first(self):
            return MagicMock(entry_hash=prev_hash["v"]) if prev_hash["v"] is not None else None

    class _Db:
        def query(self, *_a):
            return _Q()

    rows = []
    for i, (tool, decision) in enumerate(specs):
        ts = start + timedelta(minutes=i)
        prev, entry = chain_hash_for_insert(_Db(), uuid.UUID(ws), ts, tool, decision)
        prev_hash["v"] = entry
        rows.append(GuardAuditEvent(
            id=uuid.UUID(int=1000 + i), workspace_id=uuid.UUID(ws), ai_tool="claude_code",
            tool_call=tool, decision=decision, source="hook", ts=ts, previous_hash=prev,
            entry_hash=entry, input_summary=f"call {i}", rule_id="r1" if decision == "blocked" else None,
        ))
    return rows


FIXTURE_SPECS = [("Bash", "allowed"), ("Write", "warned"), (None, "blocked"),
                 ("Read", "allowed"), ("Bash", "blocked")]


def _fixture_text() -> str:
    pos = 0
    out = []
    for e in _chain_rows(WS, FIXTURE_SPECS):
        pos += 1
        out.append(ax.ndjson_line(ax.serialize_event(e, pos)))
    return "".join(out)


def test_cli_fixture_matches_current_hash_function():
    """Drift guard: the committed CLI fixture is what today's hash fn + serializer emit.
    Regenerate with UPDATE_AUDIT_FIXTURE=1."""
    import os
    text = _fixture_text()
    if os.environ.get("UPDATE_AUDIT_FIXTURE") == "1":
        FIXTURE.parent.mkdir(parents=True, exist_ok=True)
        FIXTURE.write_text(text)
    assert FIXTURE.read_text() == text
    first = json.loads(text.splitlines()[0])
    assert first["previous_hash"] == ""
    assert first["entry_hash"] == hashlib.sha256(
        f"{first['ts']}|Bash|allowed|".encode()).hexdigest()


# ── sqlite harness ────────────────────────────────────────────────────────────

@pytest.fixture
def sqlite_table():
    """PG UUID columns don't round-trip on SQLite; swap to the generic Uuid type for the test only."""
    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import UUID as PGUUID
    swapped = [(c, c.type) for c in GuardAuditEvent.__table__.columns if isinstance(c.type, PGUUID)]
    for c, _ in swapped:
        c.type = sa.Uuid(as_uuid=True)
    yield
    for c, t in swapped:
        c.type = t


@pytest.fixture
def env(sqlite_table):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    GuardAuditEvent.__table__.create(engine)
    Session = sessionmaker(bind=engine)
    seed = Session()
    seed.add_all(_chain_rows(WS, [("Bash", "allowed")] * 3 + [("Write", "blocked"), ("Bash", "warned")]))
    other = _chain_rows(OTHER_WS, [("Bash", "allowed")] * 2)
    for i, r in enumerate(other):
        r.id = uuid.UUID(int=5000 + i)
    seed.add_all(other)
    seed.commit()

    def _db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_workspace_id] = lambda: WS
    app.dependency_overrides[get_user_id] = lambda: "user_1"
    with patch.object(ax, "SessionLocal", Session), patch.object(ax, "set_workspace_rls", lambda *a: None):
        yield TestClient(app, raise_server_exceptions=False), Session
    for dep in (get_db, get_workspace_id, get_user_id):
        app.dependency_overrides.pop(dep, None)


def _qs(**extra):
    base = {"since": (T0 - timedelta(hours=1)).isoformat(), "until": (T0 + timedelta(hours=1)).isoformat()}
    return {**base, **extra}


def _ndjson(resp):
    return [json.loads(line) for line in resp.text.splitlines()]


def test_ndjson_export_full_fidelity_scoped_and_ordered(env):
    client, _ = env
    r = client.get("/guard/events/export", params=_qs())
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    rows = _ndjson(r)
    assert [x["id"] for x in rows] == [str(uuid.UUID(int=1000 + i)) for i in range(5)]
    assert {x["workspace_id"] for x in rows} == {WS}  # other workspace never appears
    assert [x["chain_position"] for x in rows] == [1, 2, 3, 4, 5]
    assert rows[0]["previous_hash"] == "" and rows[1]["previous_hash"] == rows[0]["entry_hash"]
    assert rows[3]["rule_id"] == "r1" and rows[3]["decision"] == "blocked"
    assert r.headers["x-conduct-export-capped"] == "false"


def test_content_disposition_filename(env):
    client, _ = env
    r = client.get("/guard/events/export", params=_qs(format="csv"))
    assert r.headers["content-disposition"] == 'attachment; filename="conduct-audit-2026-09-01_2026-09-01.csv"'


def test_range_filtering(env):
    client, _ = env
    since = (T0 + timedelta(minutes=1)).isoformat()
    until = (T0 + timedelta(minutes=3)).isoformat()
    rows = _ndjson(client.get("/guard/events/export", params={"since": since, "until": until}))
    assert [x["id"] for x in rows] == [str(uuid.UUID(int=1001 + i)) for i in range(3)]
    assert rows[0]["chain_position"] == 2  # position is within the full workspace chain


def test_decision_and_tool_filters(env):
    client, _ = env
    rows = _ndjson(client.get("/guard/events/export", params=_qs(decision=["block", "warn"])))
    assert sorted(x["decision"] for x in rows) == ["blocked", "warned"]
    assert all(x["chain_position"] is None for x in rows)
    rows = _ndjson(client.get("/guard/events/export", params=_qs(tool="Write")))
    assert [x["tool_call"] for x in rows] == ["Write"]


def test_csv_export(env):
    client, Session = env
    s = Session()
    ev = s.query(GuardAuditEvent).filter_by(id=uuid.UUID(int=1000)).one()
    ev.input_summary = "=HYPERLINK(\"http://x\")"
    s.commit()
    r = client.get("/guard/events/export", params=_qs(format="csv"))
    assert r.headers["content-type"].startswith("text/csv")
    parsed = list(csv.DictReader(io.StringIO(r.text)))
    assert len(parsed) == 5 and list(parsed[0].keys()) == list(ax.EXPORT_FIELDS)
    assert parsed[0]["input_summary"].startswith("'=")  # formula neutralised
    assert parsed[1]["previous_hash"] == parsed[0]["entry_hash"]


def test_cap_header_and_truncation(env):
    client, _ = env
    with patch.object(ax, "AUDIT_EXPORT_MAX_ROWS", 3):
        r = client.get("/guard/events/export", params=_qs())
    assert len(_ndjson(r)) == 3  # first N streamed
    assert r.headers["x-conduct-export-capped"] == "true"
    assert r.headers["x-conduct-export-rows"] == "3"


def test_cap_constant_is_hardcoded():
    assert ax.AUDIT_EXPORT_MAX_ROWS == 100_000


@pytest.mark.parametrize("params,code", [
    ({"since": "2026-09-02T00:00:00Z", "until": "2026-09-01T00:00:00Z"}, 400),
    ({"since": "2024-01-01T00:00:00Z", "until": "2026-01-01T00:00:00Z"}, 400),
    ({"since": "2026-09-01T00:00:00Z", "until": "2026-09-02T00:00:00Z", "format": "xml"}, 422),
    ({"since": "garbage", "until": "2026-09-02T00:00:00Z"}, 422),
    ({"until": "2026-09-02T00:00:00Z"}, 422),
])
def test_validation(env, params, code):
    client, _ = env
    assert client.get("/guard/events/export", params=params).status_code == code


def test_export_writes_audit_event(env):
    client, Session = env
    r = client.get("/guard/events/export", params=_qs(format="csv"))
    assert r.status_code == 200
    ev = Session().query(GuardAuditEvent).filter_by(tool_call="audit.export").one()
    assert ev.workspace_id == uuid.UUID(WS) and ev.clerk_user_id == "user_1"
    assert "format=csv" in ev.input_summary and "rows=5" in ev.input_summary
    assert ev.entry_hash and ev.previous_hash  # chained like every other audit row
    # a second export now includes the first export's audit row only if the range reaches "now"
    again = _ndjson(client.get("/guard/events/export", params=_qs()))
    assert len(again) == 5


def test_export_audit_row_not_in_its_own_export(env):
    client, _ = env
    now = datetime.now(timezone.utc)
    r = client.get("/guard/events/export", params={
        "since": (now - timedelta(days=1)).isoformat(), "until": (now + timedelta(days=1)).isoformat()})
    assert r.status_code == 200 and all(x["tool_call"] != "audit.export" for x in _ndjson(r))


# ── authorization ─────────────────────────────────────────────────────────────

def test_route_declares_audit_log_permission():
    from tests.test_endpoint_matrix import _discover_routes
    route = next(r for r in _discover_routes() if r["path"] == "/guard/events/export")
    assert route["method"] == "GET" and route["permissions"] == {"platform.audit_log.view"}


def test_check_permission_refuses_role_without_grant():
    from app.core.auth import check_permission
    db = MagicMock()
    # role lookup -> developer; grant lookup -> none; RBAC tables seeded.
    db.execute.return_value.fetchone.side_effect = [MagicMock(role="developer"), None, (1,)]
    with pytest.raises(HTTPException) as exc:
        check_permission(user_id="u", workspace_id=WS, credentials=None, db=db,
                         permission="platform.audit_log.view")
    assert exc.value.status_code == 403


def test_audit_write_failure_returns_503_and_streams_nothing(env):
    client, Session = env
    with patch("app.modules.guard.routers.events_export._write_audit", side_effect=RuntimeError("db down")), \
         patch.object(ax, "stream_export") as stream:
        r = client.get("/guard/events/export", params=_qs())
    assert r.status_code == 503
    assert "attachment" not in r.headers.get("content-disposition", "")
    assert '"entry_hash"' not in r.text
    stream.assert_not_called()


def test_audit_event_is_committed_before_streaming(env):
    client, Session = env
    seen = {}

    def spy(*a, **k):
        seen["committed"] = Session().query(GuardAuditEvent).filter_by(tool_call="audit.export").count()
        return iter(())

    with patch.object(ax, "stream_export", spy):
        assert client.get("/guard/events/export", params=_qs()).status_code == 200
    assert seen["committed"] == 1
    ev = Session().query(GuardAuditEvent).filter_by(tool_call="audit.export").one()
    assert "matching_rows=5" in ev.input_summary and "not the streamed row count" in ev.input_summary


def test_write_audit_helper_swallows_by_default_and_raises_on_request():
    from app.modules.guard.routers.policies_helpers import _write_audit
    db = MagicMock()
    db.add.side_effect = RuntimeError("boom")
    with patch("app.modules.guard.models.chain_hash_for_insert", return_value=("", "h")):
        _write_audit(db, uuid.UUID(WS), "t", "r", "a")  # default: swallowed
        with pytest.raises(RuntimeError):
            _write_audit(db, uuid.UUID(WS), "t", "r", "a", raise_on_error=True)
    assert db.rollback.call_count == 2


def test_endpoint_uses_strict_workspace_scoping_not_org_rollup():
    import inspect
    from app.modules.guard.routers import events_export
    assert "_org_ws_subquery" not in inspect.getsource(events_export)
    assert "_org_ws_subquery" not in inspect.getsource(ax)
