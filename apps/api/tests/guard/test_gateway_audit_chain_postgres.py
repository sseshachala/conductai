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
from app.modules.guard.models import GuardAuditEvent, chain_next


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
    with patch.object(audit, "SessionLocal", factory):
        audit.record(str(ws), "user_1", "claude-code", "anthropic", "claude-x", decision, None, 3,
                     body={}, response_bytes=b"{}", agent_identity_id=str(uuid4()))


def _hook(factory, ws, decision="allowed"):
    with factory() as db:
        ts, prev, entry = chain_next(db, ws, "bash", decision)
        db.add(GuardAuditEvent(id=uuid4(), workspace_id=ws, ai_tool="claude_code", source="hook",
                               tool_call="bash", decision=decision, ts=ts,
                               previous_hash=prev, entry_hash=entry))
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
        db.add(GuardAuditEvent(id=uuid4(), workspace_id=ws, ai_tool="x", source="hook", tool_call="t",
                               decision="allowed", ts=future, previous_hash="",
                               entry_hash=__import__("hashlib").sha256(f"{future.isoformat()}|t|allowed|".encode()).hexdigest()))
        db.commit()
    _gateway(factory, ws)
    rows = _rows(factory, ws)
    assert rows[-1].source == "gateway" and rows[-1].ts > future
    assert _verify(factory, ws)["valid"] is True
