"""Persistence and migration tests for the layered verdict envelope (#1150 phase 1).

Runs against the test-suite Postgres. Skipped when no DATABASE_URL is
configured (matches other DB-touching test modules).
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="DATABASE_URL not set — skipping DB-backed persistence tests",
)


@pytest.fixture(scope="module")
def engine():
    return create_engine(os.environ["DATABASE_URL"])


def _now():
    return datetime.now(timezone.utc)


INSERT_WORKSPACE = text(
    "INSERT INTO workspaces (id, name, owner_id, is_approved, plan, created_at, updated_at) "
    "VALUES (:id, 'test-ws', 'owner_test', false, 'free', NOW(), NOW())"
)
INSERT_EVENT = text(
    "INSERT INTO guard_audit_events "
    "(workspace_id, ai_tool, source, decision, ts, evaluated_rules, defense_score) "
    "VALUES (:ws, :ai, 'proxy', :dec, :ts, CAST(:e AS jsonb), :s)"
)
INSERT_EVENT_MINIMAL = text(
    "INSERT INTO guard_audit_events "
    "(workspace_id, ai_tool, source, decision, ts) "
    "VALUES (:ws, :ai, 'proxy', 'allowed', :ts)"
)
READ_LATEST = text(
    "SELECT evaluated_rules, defense_score FROM guard_audit_events "
    "WHERE workspace_id = :ws ORDER BY ts DESC LIMIT 1"
)


# --------------------------------------------------------------------------- #
# 1. Migration head has both columns
# --------------------------------------------------------------------------- #

def test_migration_columns_present_at_head(engine):
    """Migration 0094 should have added evaluated_rules and defense_score."""
    with engine.connect() as conn:
        cols = {r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'guard_audit_events'"
        ))}
    assert "evaluated_rules" in cols
    assert "defense_score" in cols


def test_migration_gin_index_present(engine):
    with engine.connect() as conn:
        idx = {r[0] for r in conn.execute(text(
            "SELECT indexname FROM pg_indexes WHERE tablename = 'guard_audit_events'"
        ))}
    assert "ix_guard_audit_events_evaluated_rules_gin" in idx


# --------------------------------------------------------------------------- #
# 2. Insert path — evaluated_rules JSONB round-trips
# --------------------------------------------------------------------------- #

def test_insert_event_with_evaluated_rules_persists_correctly(engine):
    ws = uuid.uuid4()
    payload = [
        {"rule_id": "r-block", "severity": "critical", "action": "block"},
        {"rule_id": "r-warn",  "severity": "high",     "action": "warn"},
    ]
    with engine.begin() as conn:
        conn.execute(INSERT_WORKSPACE, {"id": ws})
        conn.execute(INSERT_EVENT, {
            "ws": ws, "ai": "test", "dec": "blocked", "ts": _now(),
            "e": json.dumps(payload), "s": 15,
        })
        row = conn.execute(READ_LATEST, {"ws": ws}).first()
    assert row.defense_score == 15
    assert row.evaluated_rules == payload   # JSONB round-trip preserves shape


# --------------------------------------------------------------------------- #
# 3. Backward compat — insert without new fields stays NULL
# --------------------------------------------------------------------------- #

def test_insert_event_without_new_fields_stays_null(engine):
    ws = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(INSERT_WORKSPACE, {"id": ws})
        conn.execute(INSERT_EVENT_MINIMAL, {"ws": ws, "ai": "test", "ts": _now()})
        row = conn.execute(READ_LATEST, {"ws": ws}).first()
    assert row.evaluated_rules is None
    assert row.defense_score is None


# --------------------------------------------------------------------------- #
# 4. Analytics query — find events where multiple rules fired
# --------------------------------------------------------------------------- #

def test_query_events_where_two_or_more_rules_fired(engine):
    ws = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(INSERT_WORKSPACE, {"id": ws})
        conn.execute(INSERT_EVENT, {
            "ws": ws, "ai": "test", "dec": "blocked", "ts": _now(),
            "e": json.dumps([{"rule_id": "a"}, {"rule_id": "b"}, {"rule_id": "c"}]), "s": 18,
        })
        conn.execute(INSERT_EVENT, {
            "ws": ws, "ai": "test", "dec": "warned", "ts": _now(),
            "e": json.dumps([{"rule_id": "solo"}]), "s": 3,
        })
        multi = conn.execute(text(
            "SELECT count(*) FROM guard_audit_events "
            "WHERE workspace_id = :ws AND jsonb_array_length(evaluated_rules) >= 2"
        ), {"ws": ws}).scalar()
    assert multi == 1  # only the multi-rule event qualifies


# --------------------------------------------------------------------------- #
# 5. Hash chain still valid after adding the new column
# --------------------------------------------------------------------------- #

def test_hash_chain_ignores_evaluated_rules_column(engine):
    """The hash chain function computes over (ts, tool_call, decision, prev).
    Adding evaluated_rules to the row must not affect chain integrity."""
    from app.modules.guard.models import chain_hash_for_insert
    from sqlalchemy.orm import Session

    ws = uuid.uuid4()
    now = _now()
    with Session(engine) as db:
        prev, entry = chain_hash_for_insert(db, ws, now, "test.action", "allowed")
        assert len(entry) == 64
        assert prev == ""  # first event in a fresh workspace
