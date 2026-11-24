"""The per-identity activity rollup must not stall GET /agent-identities.

Real Postgres: statement_timeout and savepoints are what is under test.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.database import SessionLocal
from app.modules.agent_identity import activity_stats as a


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        session.execute(text("SELECT 1"))
    except OperationalError:
        session.close()
        pytest.skip("Postgres not reachable")
    yield session
    session.rollback()
    session.close()


def _timeout(db) -> str:
    return db.execute(text("SELECT current_setting('statement_timeout')")).scalar()


def test_slow_rollup_degrades_to_empty_and_keeps_session_usable(db, monkeypatch):
    monkeypatch.setattr(a, "_ACTIVITY_TIMEOUT", "50ms")
    monkeypatch.setattr(a, "_query", lambda s, ws: s.execute(text("SELECT pg_sleep(2)")).all())
    before = _timeout(db)

    assert a._bounded_query(db, str(uuid.uuid4())) == {}
    assert _timeout(db) == before
    assert db.execute(text("SELECT 1")).scalar() == 1


def test_rollup_restores_statement_timeout_on_success(db):
    before = _timeout(db)

    assert a._bounded_query(db, str(uuid.uuid4())) == {}
    assert _timeout(db) == before
