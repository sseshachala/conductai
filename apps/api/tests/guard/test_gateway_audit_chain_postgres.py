"""Gateway audit rows join the workspace hash chain (PostgreSQL).

Covers: gateway rows carry previous/entry hashes, mixed gateway + hook-style
writers verify as one chain, and concurrent writers never fork the chain.
"""
from __future__ import annotations

import threading
from datetime import datetime, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import settings
from app.modules.guard.audit_retention import verify_audit_history
from app.modules.guard.models import GuardAuditEvent, chain_begin, chain_seal


@pytest.fixture
def chain_db():
    url = settings.sqlalchemy_database_url
    if not url.startswith("postgresql"):
        pytest.skip("needs PostgreSQL")
    import app.main  # noqa: F401 — register ORM relationships
    schema = "gw_chain_" + uuid4().hex[:12]
    admin = create_engine(url)
    try:
        with admin.begin() as conn:
            conn.execute(CreateSchema(schema))
            conn.execute(text(f'CREATE TABLE "{schema}".guard_audit_events '
                              "(LIKE public.guard_audit_events INCLUDING DEFAULTS)"))
            conn.execute(text(f'CREATE TABLE "{schema}".guard_policy_cache '
                              "(LIKE public.guard_policy_cache INCLUDING DEFAULTS)"))
    except Exception as exc:  # noqa: BLE001
        admin.dispose()
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    engine = create_engine(url, pool_size=8, connect_args={"options": f"-csearch_path={schema},public"})
    factory = sessionmaker(bind=engine)
    try:
        yield factory, uuid4()
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(DropSchema(schema, cascade=True))
        admin.dispose()


def _gateway(factory, ws, decision="allowed"):
    from app.guard import audit
    with patch.object(audit, "SessionLocal", factory), \
         patch.object(audit, "_audit_tokens_and_cost", lambda **_: (None, None, None)):
        audit.record(str(ws), "user_1", "claude-code", "anthropic", "claude-x", decision, None, 3,
                     body={}, response_bytes=b"{}", agent_identity_id=str(uuid4()))


def _hook(factory, ws, decision="allowed"):
    with factory() as db:
        ts, prev = chain_begin(db, ws)
        db.add(chain_seal(GuardAuditEvent(id=uuid4(), workspace_id=ws, ai_tool="claude_code", source="hook",
                                          tool_call="bash", decision=decision, ts=ts,
                                          previous_hash=prev)))
        db.commit()


def _rows(factory, ws):
    with factory() as db:
        return (db.query(GuardAuditEvent).filter(GuardAuditEvent.workspace_id == ws)
                .order_by(GuardAuditEvent.ts, GuardAuditEvent.id).all())


def _verify(factory, ws):
    with factory() as db:
        return verify_audit_history(db, ws)


def test_gateway_rows_are_hash_chained(chain_db):
    factory, ws = chain_db
    _gateway(factory, ws)
    _gateway(factory, ws, "blocked")
    rows = _rows(factory, ws)
    assert [r.source for r in rows] == ["gateway", "gateway"]
    assert all(r.entry_hash for r in rows)
    assert rows[0].previous_hash == "" and rows[1].previous_hash == rows[0].entry_hash
    assert _verify(factory, ws)["valid"] is True


def test_gateway_and_hook_rows_form_one_chain(chain_db):
    factory, ws = chain_db
    for i in range(6):
        (_gateway if i % 2 else _hook)(factory, ws)
    result = _verify(factory, ws)
    assert result["valid"] is True and result["total"] == 6


def test_concurrent_writers_do_not_fork_the_chain(chain_db):
    factory, ws = chain_db
    errors: list[BaseException] = []

    def worker(fn):
        try:
            for _ in range(5):
                fn(factory, ws)
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(_gateway if i % 2 else _hook,)) for i in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    rows = _rows(factory, ws)
    assert len(rows) == 30
    prevs = [r.previous_hash for r in rows]
    assert len(set(prevs)) == len(prevs), "two rows share a previous_hash (chain fork)"
    assert _verify(factory, ws)["valid"] is True


def test_chain_ts_never_goes_backwards(chain_db):
    """An instance whose clock is behind still appends after the tail."""
    from datetime import timedelta
    factory, ws = chain_db
    future = datetime.now(timezone.utc) + timedelta(seconds=5)
    with factory() as db:
        db.add(chain_seal(GuardAuditEvent(id=uuid4(), workspace_id=ws, ai_tool="x", source="hook", tool_call="t",
                                          decision="allowed", ts=future, previous_hash="")))
        db.commit()
    _gateway(factory, ws)
    rows = _rows(factory, ws)
    assert rows[-1].source == "gateway" and rows[-1].ts > future
    assert _verify(factory, ws)["valid"] is True


# ── chain v2 (#2421): full-record hash, versioned ──────────────────────────────

def _legacy_row(factory, ws, ts, prev):
    """A row exactly as written before v2: 4-field hash, hash_version left at its default."""
    from app.modules.guard.audit_chain import compute_v1
    with factory() as db:
        db.add(GuardAuditEvent(id=uuid4(), workspace_id=ws, ai_tool="claude_code", source="hook",
                               tool_call="bash", decision="allowed", ts=ts, previous_hash=prev,
                               entry_hash=compute_v1(ts, "bash", "allowed", prev)))
        db.commit()


def test_new_rows_are_v2_and_recompute_from_db_values(chain_db):
    from app.modules.guard.audit_chain import expected_hash
    from app.modules.guard.audit_retention import _snapshot
    factory, ws = chain_db
    _hook(factory, ws)
    _gateway(factory, ws, "blocked")
    rows = _rows(factory, ws)
    assert [r.hash_version for r in rows] == [2, 2]
    prev = ""
    for r in rows:  # hash computed at write time == hash recomputed from stored values
        assert expected_hash(_snapshot(r), prev) == r.entry_hash
        prev = r.entry_hash


def test_v1_history_then_v2_rows_verify_clean(chain_db):
    from datetime import timedelta
    factory, ws = chain_db
    t0 = datetime.now(timezone.utc) - timedelta(days=2)
    _legacy_row(factory, ws, t0, "")
    first = _rows(factory, ws)[0]
    assert first.hash_version == 1
    _legacy_row(factory, ws, t0 + timedelta(seconds=1), first.entry_hash)
    _hook(factory, ws)       # boundary row links to the last v1 entry_hash
    _gateway(factory, ws)
    rows = _rows(factory, ws)
    assert [r.hash_version for r in rows] == [1, 1, 2, 2]
    assert rows[2].previous_hash == rows[1].entry_hash
    assert _verify(factory, ws)["valid"] is True


@pytest.mark.parametrize("column,value", [
    ("input_summary", "tampered"), ("user_email", "x@example.com"), ("rule_message", "x"),
    ("hook_session_id", "other"), ("route", "/x"), ("defense_score", 99), ("cost_usd_after", 9.5),
    ("tokens_before", 7), ("provider", "other"), ("policy_hash", "ff"),
    ("routing_meta", {"a": 1}), ("evaluated_rules", [{"rule_id": "x"}]),
])
def test_tampering_any_v2_field_breaks_verify(chain_db, column, value):
    factory, ws = chain_db
    _hook(factory, ws)
    _gateway(factory, ws)
    assert _verify(factory, ws)["valid"] is True
    victim = _rows(factory, ws)[0]
    with factory() as db:
        db.query(GuardAuditEvent).filter(GuardAuditEvent.id == victim.id).update({column: value})
        db.commit()
    result = _verify(factory, ws)
    assert result["valid"] is False
    assert result["broken_at"] == victim.ts.isoformat()


# ── known append-race forks (#2524 item 1) ─────────────────────────────────────

def _fork_rows(factory, ws, base):
    """a -> b and a -> c (fork), then d links to c: every entry_hash is individually correct."""
    from datetime import timedelta
    from app.modules.guard.audit_chain import compute_v1
    spec = [("a", ""), ("b", "a"), ("c", "a"), ("d", "c")]
    hashes: dict[str, str] = {}
    with factory() as db:
        for i, (name, parent) in enumerate(spec):
            ts = base + timedelta(seconds=i)
            prev = hashes.get(parent, "")
            hashes[name] = compute_v1(ts, name, "allowed", prev)
            db.add(GuardAuditEvent(id=uuid4(), workspace_id=ws, ai_tool="x", source="hook", tool_call=name,
                                   decision="allowed", ts=ts, previous_hash=prev, entry_hash=hashes[name]))
        db.commit()


def test_pre_fix_fork_is_reported_as_known_append_race(chain_db):
    from datetime import timedelta
    from app.modules.guard.audit_chain import APPEND_RACE_FIXED_AT
    factory, ws = chain_db
    _fork_rows(factory, ws, APPEND_RACE_FIXED_AT - timedelta(days=10))
    result = _verify(factory, ws)
    assert result["valid"] is True and result["broken_at"] is None
    assert result["known_append_races"] == 1
    assert result["known_append_race_details"][0]["sibling_id"]


def test_post_fix_fork_is_reported_as_broken(chain_db):
    from datetime import timedelta
    from app.modules.guard.audit_chain import APPEND_RACE_FIXED_AT
    factory, ws = chain_db
    _fork_rows(factory, ws, APPEND_RACE_FIXED_AT + timedelta(days=1))
    result = _verify(factory, ws)
    assert result["valid"] is False and result["broken_at"] is not None


def test_fork_with_a_tampered_row_is_still_broken(chain_db):
    from datetime import timedelta
    from app.modules.guard.audit_chain import APPEND_RACE_FIXED_AT
    factory, ws = chain_db
    _fork_rows(factory, ws, APPEND_RACE_FIXED_AT - timedelta(days=10))
    with factory() as db:
        db.query(GuardAuditEvent).filter(GuardAuditEvent.tool_call == "c").update({"decision": "blocked"})
        db.commit()
    assert _verify(factory, ws)["valid"] is False
