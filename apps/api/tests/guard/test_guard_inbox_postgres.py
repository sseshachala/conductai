"""Real PostgreSQL regressions for guard_inbox — trigger + backfill.

Set ``GUARD_INBOX_TEST_DATABASE_URL`` to a disposable local database. Each
test creates and drops its own random schema; no existing application
rows are used. CI (see ``.github/workflows/ci.yml``) sets the env var so
the file is exercised on every PR — not permanently skipped.

Coverage (reviewer requirements against #2170-follow-up Inbox correctness):

- Severity escalates on ``warned → blocked``; never downgrades on
  ``blocked → warned``.
- Resolved-finding preservation across ``backfill`` (only the genuine
  trigger re-fire path is allowed to reopen).
- Backfill idempotency: run twice, occurrences equals the count of
  qualifying audit events both times.
- Duplicate groups within a single backfill collapse correctly (the
  SELECT DISTINCT + aggregate handles them).
- Concurrent live insert during backfill — the trigger's ``+1`` lands
  on top of the reconciled count, not lost.
- Older-history backfill into a finding with newer live activity:
  first_seen_at goes earlier, last_seen_at + latest_event_id stay
  where the newer live event put them.
"""
from __future__ import annotations

import importlib.util
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Barrier

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, text
from sqlalchemy.schema import CreateSchema, DropSchema


WS = uuid.UUID("11111111-1111-4111-8111-111111111111")


# ── Fixture: fresh schema with pgcrypto + trigger stack ───────────────────


def _load_migration(rel_path: str):
    """Import an alembic migration file by relative path so we can call
    its .upgrade() directly against our test-schema connection."""
    path = Path(__file__).resolve().parents[2] / "alembic/versions" / rel_path
    spec = importlib.util.spec_from_file_location(f"_mig_{rel_path}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The trigger reads NEW.workspace_id, NEW.rule_id, NEW.source,
# NEW.rule_message, NEW.decision, NEW.id, NEW.ts. Nothing else.
_MINIMAL_AUDIT_TABLE = """
CREATE TABLE guard_audit_events (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id  uuid NOT NULL,
    ts            timestamptz NOT NULL DEFAULT now(),
    decision      text NOT NULL,
    rule_id       text,
    source        text,
    rule_message  text
);
"""


@pytest.fixture
def database():
    url = os.environ.get("GUARD_INBOX_TEST_DATABASE_URL")
    if not url:
        pytest.skip("GUARD_INBOX_TEST_DATABASE_URL not set")
    schema = "guard_inbox_test_" + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with engine.begin() as connection:
            # pgcrypto is public-schema; make sure the schema search path
            # sees digest()/gen_random_uuid() by qualifying via
            # search_path=schema,public in the schema fixture below.
            connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
            connection.execute(text(_MINIMAL_AUDIT_TABLE))
            # 0123 creates guard_inbox + INSERT trigger + trigger fn.
            # 0133 attaches the UPDATE OF decision trigger.
            # 0147 replaces the trigger fn with severity escalation.
            mig_0123 = _load_migration("0123_drop_security_loop_add_guard_inbox.py")
            mig_0133 = _load_migration("0133_guard_inbox_trg_lifecycle.py")
            mig_0147 = _load_migration("0147_guard_inbox_severity_escalation.py")
            # 0123's upgrade also DROPs security tables that don't
            # exist in our minimal schema — the IF EXISTS in that
            # migration keeps those calls no-op, so the rest of the
            # migration runs.
            with Operations.context(MigrationContext.configure(connection)):
                mig_0123.upgrade()
                mig_0133.upgrade()
                mig_0147.upgrade()
        # Reset search_path on each connection so pgcrypto (public) is
        # visible to the trigger.
        engine = create_engine(
            url, connect_args={"options": f"-csearch_path={schema},public"},
        )
        yield engine, schema
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


# ── Helpers ───────────────────────────────────────────────────────────────


def _insert_event(
    conn,
    *,
    decision: str,
    rule_id: str = "rule-1",
    source: str = "test",
    message: str = "example",
    ts: datetime | None = None,
    workspace_id: uuid.UUID = WS,
) -> uuid.UUID:
    event_id = uuid.uuid4()
    conn.execute(
        text("""
            INSERT INTO guard_audit_events
                (id, workspace_id, ts, decision, rule_id, source, rule_message)
            VALUES (:id, :ws, :ts, :d, :r, :s, :m)
        """),
        {
            "id": event_id,
            "ws": workspace_id,
            "ts": ts or datetime.now(timezone.utc),
            "d": decision,
            "r": rule_id,
            "s": source,
            "m": message,
        },
    )
    return event_id


def _one_inbox_row(conn, workspace_id: uuid.UUID = WS) -> dict:
    row = conn.execute(
        text("""
            SELECT id, dedup_key, severity, occurrences, status,
                   first_seen_at, last_seen_at, latest_event_id,
                   resolved_reason, resolved_at, resolved_by, resolved_note
              FROM guard_inbox
             WHERE workspace_id = :ws
        """),
        {"ws": workspace_id},
    ).one()
    return dict(row._mapping)


def _run_backfill(engine, workspace_id: uuid.UUID, days: int = 30):
    from app.modules.guard.routers.inbox import _BACKFILL_SQL
    with engine.begin() as conn:
        result = conn.execute(text(_BACKFILL_SQL), {"ws": workspace_id, "days": days})
        row = result.one()
    return {"inserted": int(row.inserted or 0), "reconciled": int(row.reconciled or 0)}


# ── Trigger: severity escalation (#2170-follow-up) ────────────────────────


def test_warned_then_blocked_escalates_severity_to_critical(database):
    engine, _ = database
    with engine.begin() as conn:
        _insert_event(conn, decision="warned")
    with engine.begin() as conn:
        _insert_event(conn, decision="blocked")  # same dedup key
    with engine.begin() as conn:
        row = _one_inbox_row(conn)
    assert row["occurrences"] == 2
    assert row["severity"] == "critical", (
        f"warned → blocked must escalate; got severity={row['severity']!r}"
    )


def test_blocked_then_warned_does_not_downgrade_severity(database):
    engine, _ = database
    with engine.begin() as conn:
        _insert_event(conn, decision="blocked")
    with engine.begin() as conn:
        _insert_event(conn, decision="warned")
    with engine.begin() as conn:
        row = _one_inbox_row(conn)
    assert row["occurrences"] == 2
    assert row["severity"] == "critical", (
        f"blocked → warned must NOT downgrade; got severity={row['severity']!r}"
    )


def test_approved_then_warned_escalates_to_medium(database):
    engine, _ = database
    with engine.begin() as conn:
        _insert_event(conn, decision="approved")
    with engine.begin() as conn:
        _insert_event(conn, decision="warned")
    with engine.begin() as conn:
        row = _one_inbox_row(conn)
    assert row["severity"] == "medium"


# ── Trigger: existing auto-reopen preserved ───────────────────────────────


def test_resolved_finding_reopens_on_new_audit_event(database):
    """Baseline: the trigger's auto-reopen behavior still fires (0123)."""
    engine, _ = database
    with engine.begin() as conn:
        _insert_event(conn, decision="warned")
    # Resolve it.
    now = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE guard_inbox
               SET status = 'resolved',
                   resolved_reason = 'expected',
                   resolved_at = :ts,
                   resolved_by = 'operator'
             WHERE workspace_id = :ws
        """), {"ts": now, "ws": WS})
    # A new same-dedup event → trigger fires → row must reopen.
    with engine.begin() as conn:
        _insert_event(conn, decision="warned")
    with engine.begin() as conn:
        row = _one_inbox_row(conn)
    assert row["status"] == "open"
    assert row["resolved_reason"] is None
    assert row["resolved_at"] is None
    assert row["resolved_by"] is None


# ── Backfill correctness ──────────────────────────────────────────────────


def test_backfill_is_idempotent_on_occurrences(database):
    """Reviewer P1: re-running backfill must NOT inflate occurrences.
    Setup: 3 same-dedup events. Backfill twice. occurrences=3 both times.
    """
    engine, _ = database
    with engine.begin() as conn:
        _insert_event(conn, decision="warned")
        _insert_event(conn, decision="warned")
        _insert_event(conn, decision="warned")
    with engine.begin() as conn:
        assert _one_inbox_row(conn)["occurrences"] == 3

    first = _run_backfill(engine, WS, days=30)
    with engine.begin() as conn:
        assert _one_inbox_row(conn)["occurrences"] == 3
    assert first["reconciled"] == 1

    second = _run_backfill(engine, WS, days=30)
    with engine.begin() as conn:
        assert _one_inbox_row(conn)["occurrences"] == 3
    assert second["reconciled"] == 1


def test_backfill_never_reopens_resolved_findings(database):
    """Reviewer P1: repair pass must NOT touch resolution metadata."""
    engine, _ = database
    with engine.begin() as conn:
        _insert_event(conn, decision="warned")
    resolved_at = datetime.now(timezone.utc)
    with engine.begin() as conn:
        conn.execute(text("""
            UPDATE guard_inbox
               SET status = 'resolved',
                   resolved_reason = 'false_positive',
                   resolved_at = :ts,
                   resolved_by = 'operator@example.com',
                   resolved_note = 'noise'
             WHERE workspace_id = :ws
        """), {"ts": resolved_at, "ws": WS})

    _run_backfill(engine, WS, days=30)

    with engine.begin() as conn:
        row = _one_inbox_row(conn)
    assert row["status"] == "resolved", "backfill reopened a resolved finding"
    assert row["resolved_reason"] == "false_positive"
    assert row["resolved_by"] == "operator@example.com"
    assert row["resolved_note"] == "noise"
    assert row["resolved_at"] is not None


def test_backfill_preserves_newer_last_seen_and_latest_event(database):
    """Reviewer P1: backfilling older history must NOT regress
    ``last_seen_at`` or replace ``latest_event_id`` with an older event.
    """
    engine, _ = database
    # Older event first, then a much-newer live one.
    old_ts = datetime.now(timezone.utc) - timedelta(days=10)
    new_ts = datetime.now(timezone.utc)
    with engine.begin() as conn:
        _insert_event(conn, decision="warned", ts=old_ts)
    with engine.begin() as conn:
        new_id = _insert_event(conn, decision="warned", ts=new_ts)
    with engine.begin() as conn:
        before = _one_inbox_row(conn)
    assert before["latest_event_id"] == new_id

    # Now backfill the wider window — its authoritative aggregate has
    # the same events but must not clobber ``latest_event_id`` with the
    # older one.
    _run_backfill(engine, WS, days=90)

    with engine.begin() as conn:
        after = _one_inbox_row(conn)
    assert after["latest_event_id"] == new_id
    assert after["last_seen_at"] == before["last_seen_at"]
    # first_seen_at is the older event's ts either way.
    assert after["first_seen_at"] == before["first_seen_at"]


def test_backfill_escalates_severity_never_downgrades(database):
    """Multiple decisions in history — severity comes from the max."""
    engine, _ = database
    with engine.begin() as conn:
        _insert_event(conn, decision="warned")  # medium
        _insert_event(conn, decision="blocked")  # critical
        _insert_event(conn, decision="approved")  # low
    # A subsequent overriding UPDATE to 'medium' would be wrong even if
    # the trigger did it; backfill must confirm severity=critical.
    _run_backfill(engine, WS, days=30)
    with engine.begin() as conn:
        row = _one_inbox_row(conn)
    assert row["severity"] == "critical"
    assert row["occurrences"] == 3


def test_backfill_duplicate_groups_collapse(database):
    """A single backfill run over N repeat events for the same group
    still ends with occurrences = N (aggregate collapses them)."""
    engine, _ = database
    with engine.begin() as conn:
        for _ in range(5):
            _insert_event(conn, decision="warned")
    # Simulate a rebuild-from-scratch: drop the inbox row then backfill.
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM guard_inbox WHERE workspace_id = :ws"), {"ws": WS})

    result = _run_backfill(engine, WS, days=30)
    assert result["inserted"] == 1
    assert result["reconciled"] == 0
    with engine.begin() as conn:
        assert _one_inbox_row(conn)["occurrences"] == 5


def test_backfill_survives_concurrent_live_insert(database):
    """Reviewer P1: a live audit-event trigger firing concurrently with
    a backfill run must not have its ``+1`` lost. The backfill locks
    the inbox row; the trigger's ON CONFLICT DO UPDATE waits, then
    increments on top of the reconciled count.
    """
    engine, _ = database
    # Seed 3 events so an inbox row exists.
    with engine.begin() as conn:
        for _ in range(3):
            _insert_event(conn, decision="warned")

    barrier = Barrier(2)

    def run_backfill():
        # Signal ready, then run the reconciliation. Both threads
        # release from the barrier together so the trigger insert is
        # racing the FOR UPDATE lock.
        barrier.wait()
        return _run_backfill(engine, WS, days=30)

    def run_insert():
        barrier.wait()
        with engine.begin() as conn:
            _insert_event(conn, decision="warned")

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_bf = pool.submit(run_backfill)
        f_in = pool.submit(run_insert)
        f_bf.result(timeout=30)
        f_in.result(timeout=30)

    with engine.begin() as conn:
        row = _one_inbox_row(conn)
    # Whether the trigger's insert happened before or after the
    # backfill's snapshot, the row must end at exactly 4 (3 seeded + 1
    # concurrent). If the count is 3 the +1 was lost; if 5 the backfill
    # double-counted.
    assert row["occurrences"] == 4, (
        f"expected occurrences=4 after concurrent insert; "
        f"got {row['occurrences']} — trigger update was lost"
    )
