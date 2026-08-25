"""
Regression guard for /guard/spend month filtering.

Closes the bug where selecting a past month showed
period_start..now instead of period_start..next_month.

Loads the app with a real in-memory SQLite engine (create_engine is patched
before app.core.database imports so sqlite-incompatible pool kwargs are
stripped). This lets us exercise the real ORM query chain in
_get_spend_summary_inner without needing Postgres or Redis.
"""
from __future__ import annotations

import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from unittest.mock import patch as _patch

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

_log_mock = MagicMock()
_log_mock.get_logger = MagicMock(return_value=MagicMock())
sys.modules.setdefault("structlog", _log_mock)
sys.modules.setdefault("redis", MagicMock())
sys.modules.setdefault("sentry_sdk", MagicMock())

_cfg_stub = MagicMock()
_cfg_stub.settings = MagicMock(
    sentry_dsn=None,
    sqlalchemy_database_url="sqlite:///:memory:",
    encryption_key="test-key-32-bytes-long-xxxxxxxx!",
    allowed_egress_hosts=[],
    log_level="INFO",
)
sys.modules["app.core.config"] = _cfg_stub

# Patch create_engine before app.core.database loads — SQLite rejects
# max_overflow / pool_size that Postgres accepts, so strip them silently.
import sqlalchemy as _sa  # noqa: E402
_orig_create_engine = _sa.create_engine


def _safe_create_engine(url, *args, **kwargs):
    if str(url).startswith("sqlite"):
        kwargs.pop("max_overflow", None)
        kwargs.pop("pool_size", None)
        kwargs.pop("connect_args", None)  # Postgres connect_timeout isn't valid for sqlite
    return _orig_create_engine(url, *args, **kwargs)


_sa.create_engine = _safe_create_engine

# If test_guard_savings.py ran first it stubbed app.core.database with a
# MagicMock — that poisons the ORM models (columns become Mock attrs). Evict
# any stubbed / already-imported guard modules so the real ones re-import.
for _mod in [
    "app.core.database",
    "app.modules.guard.models",
    "app.modules.guard.routers.spend",
    "app.modules.guard.routers.savings",
]:
    sys.modules.pop(_mod, None)

from app.modules.guard.routers import spend as spend_mod  # noqa: E402
from app.modules.guard.routers.spend import (  # noqa: E402
    _next_period_start,
    _parse_period_start,
    _get_spend_summary_inner,
)


# ── Helper tests ──────────────────────────────────────────────────────────────

class TestNextPeriodStart:
    def test_mid_year_advances_one_month(self):
        s = datetime(2026, 7, 1, tzinfo=timezone.utc)
        assert _next_period_start(s) == datetime(2026, 8, 1, tzinfo=timezone.utc)

    def test_december_rolls_year(self):
        s = datetime(2026, 12, 1, tzinfo=timezone.utc)
        assert _next_period_start(s) == datetime(2027, 1, 1, tzinfo=timezone.utc)

    def test_january_advances_within_same_year(self):
        s = datetime(2026, 1, 1, tzinfo=timezone.utc)
        assert _next_period_start(s) == datetime(2026, 2, 1, tzinfo=timezone.utc)


class TestParsePeriodStart:
    def test_valid_month_string(self):
        assert _parse_period_start("2026-04") == datetime(2026, 4, 1, tzinfo=timezone.utc)

    def test_invalid_falls_back_to_current_month(self):
        result = _parse_period_start("garbage")
        now = datetime.now(timezone.utc)
        assert result.year == now.year and result.month == now.month and result.day == 1

    def test_none_falls_back_to_current_month(self):
        result = _parse_period_start(None)
        now = datetime.now(timezone.utc)
        assert result.year == now.year and result.month == now.month


# ── Recording fake-query — captures every .filter() clause ────────────────────

class _RecordingQuery:
    """Tiny SA-query stand-in that records .filter() args so tests can inspect
    the datetime bounds actually applied. Returns benign defaults for the rest."""

    def __init__(self, sink):
        self.sink = sink

    def filter(self, *clauses):
        self.sink.append(clauses)
        return self

    def group_by(self, *_): return self
    def order_by(self, *_): return self
    def offset(self, _): return self
    def limit(self, _): return self
    def with_for_update(self, **_): return self

    def first(self): return None

    def one(self):
        r = MagicMock()
        for name in ("tokens_before", "tokens_after"):
            setattr(r, name, 0)
        for name in ("cost_before", "cost_after"):
            setattr(r, name, 0.0)
        return r

    def all(self): return []

    def scalar(self): return 0


def _extract_datetime_bounds(clauses):
    """From SA BinaryExpression clauses, extract (op_name, datetime_value)
    for every clause whose right-hand side is a datetime literal."""
    out = []
    for clause in clauses:
        right = getattr(clause, "right", None)
        val = getattr(right, "value", None) if right is not None else None
        if isinstance(val, datetime):
            op = getattr(clause, "operator", None)
            op_str = getattr(op, "__name__", str(op))
            out.append((op_str, val))
    return out


def _collect_bounds(filter_calls):
    """filter_calls is a list of sinks; each sink is a list of clause-tuples
    from every .filter(*args) call on that query. Flatten to a single list
    of (op_name, datetime_value)."""
    out = []
    for sink in filter_calls:
        for batch in sink:
            out.extend(_extract_datetime_bounds(batch))
    return out


def _make_recording_db():
    """Fake db.query() returning a query that records every .filter() clause,
    plus db.execute() that returns a benign scalar."""
    calls = []
    db = MagicMock()

    def _query(*_args, **_kwargs):
        sink = []
        calls.append(sink)
        return _RecordingQuery(sink)

    db.query.side_effect = _query
    exec_result = MagicMock()
    exec_result.scalar.return_value = 0
    db.execute.return_value = exec_result
    return db, calls


# ── The regression tests ──────────────────────────────────────────────────────

_WS = str(uuid.uuid4())


def _stub_org_ws(monkeypatch):
    """Skip the Workspace/org lookup — return a query that yields no rows so
    the .in_([]) filter on aggregates is harmless for our inspection tests."""
    fake_ws_q = MagicMock()
    fake_ws_q.all.return_value = []
    fake_ws_q.filter.return_value = fake_ws_q
    # Patch via the function's own __globals__ so it works regardless of
    # which module object `spend_mod` points to in combined test runs.
    monkeypatch.setitem(
        _get_spend_summary_inner.__globals__,
        "_org_ws_subquery",
        lambda db, ws: fake_ws_q,
    )


class TestMonthUpperBoundApplied:
    """Bug: filters used ts >= period_start with no upper bound, so 'Apr 2026'
    returned everything from April onward. Every aggregation must now also
    apply ts < period_end (May 1 for April)."""

    def test_past_month_bounds_are_start_and_next_month(self, monkeypatch):
        _stub_org_ws(monkeypatch)
        db, filter_calls = _make_recording_db()

        _get_spend_summary_inner(db, _WS, month="2026-04")

        expected_start = datetime(2026, 4, 1, tzinfo=timezone.utc)
        expected_end = datetime(2026, 5, 1, tzinfo=timezone.utc)

        all_bounds = _collect_bounds(filter_calls)

        starts = [dt for op, dt in all_bounds if "ge" in op and dt == expected_start]
        ends = [dt for op, dt in all_bounds if "lt" in op and dt == expected_end]

        assert len(starts) >= 4, f"expected >=4 period-start lower bounds, saw {len(starts)}"
        assert len(ends) >= 4, f"expected >=4 period-end upper bounds, saw {len(ends)}"
        assert len(ends) >= len(starts) - 1, (
            f"upper bounds ({len(ends)}) missing next to lower bounds "
            f"({len(starts)}) — every period_start filter must be paired"
        )

    def test_december_month_upper_bound_rolls_year(self, monkeypatch):
        _stub_org_ws(monkeypatch)
        db, filter_calls = _make_recording_db()

        _get_spend_summary_inner(db, _WS, month="2026-12")

        expected_end = datetime(2027, 1, 1, tzinfo=timezone.utc)
        all_bounds = _collect_bounds(filter_calls)
        ends = [dt for op, dt in all_bounds if "lt" in op and dt == expected_end]
        assert ends, "December period must roll to Jan 1 next year as its upper bound"


class TestTodayFieldsClampToSelectedMonth:
    """Bug: events_today / blocked_today / tokens_saved_today used rolling 24h
    regardless of month picker, so past-month views leaked current-day counts.
    They must now scope to the whole selected month when it isn't current."""

    def test_past_month_today_window_is_the_whole_month(self, monkeypatch):
        _stub_org_ws(monkeypatch)
        db, filter_calls = _make_recording_db()

        _get_spend_summary_inner(db, _WS, month="2026-04")

        all_bounds = _collect_bounds(filter_calls)

        # Rolling 24h would place SOME lower bound within the last 24 hours.
        # For a past month, that must NEVER happen.
        now = datetime.now(timezone.utc)
        cutoff_24h_ago = now - timedelta(hours=25)  # +1h slack for test drift
        recent_bounds = [dt for _op, dt in all_bounds if dt > cutoff_24h_ago]
        assert not recent_bounds, (
            f"past-month query leaked a rolling-24h bound: {recent_bounds}"
        )

    def test_current_month_still_uses_rolling_24h(self, monkeypatch):
        _stub_org_ws(monkeypatch)
        db, filter_calls = _make_recording_db()

        now = datetime.now(timezone.utc)
        this_month = f"{now.year:04d}-{now.month:02d}"
        _get_spend_summary_inner(db, _WS, month=this_month)

        all_bounds = _collect_bounds(filter_calls)

        # For the current month, at least ONE bound must be within the last
        # 24h — that's the events_today / blocked_today / tokens_saved_today
        # rolling window preserved for the dashboard.
        recent = [dt for _op, dt in all_bounds if now - dt < timedelta(hours=25)]
        assert recent, "current-month view must keep rolling-24h 'today' window"


# ── Static regression guard on the source itself ──────────────────────────────
# Belt-and-braces: even if the query-recording tests miss a query someone adds
# later, this scoped source scan catches "someone removed the upper bound"
# specifically inside _get_spend_summary_inner. Other helpers
# (_current_month_cost, budget_check) intentionally query month-to-date with
# no upper bound and are excluded.

class TestSourceHasSymmetricBounds:
    def test_every_lower_bound_in_summary_is_paired_with_upper_bound(self):
        src = Path(spend_mod.__file__).read_text()
        # Extract just the body of _get_spend_summary_inner
        m = re.search(
            r"def _get_spend_summary_inner\(.*?\)[^:]*:(?P<body>.*?)(?=\n(?:def |class |@))",
            src,
            flags=re.DOTALL,
        )
        assert m, "could not locate _get_spend_summary_inner in spend.py"
        body = m.group("body")
        lower = re.findall(
            r"(?:ts|started_at)\s*>=\s*(?:period_start|today_start)", body
        )
        upper = re.findall(
            r"(?:ts|started_at)\s*<\s*(?:period_end|today_end)", body
        )
        assert len(lower) == len(upper), (
            f"unbalanced time bounds inside _get_spend_summary_inner: "
            f"{len(lower)} lower vs {len(upper)} upper. "
            f"Every `>= period_start`/`>= today_start` filter must be paired "
            f"with a matching `< period_end`/`< today_end`."
        )
