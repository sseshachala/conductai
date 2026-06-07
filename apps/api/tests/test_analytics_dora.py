"""
Unit tests for get_dora in app.routers.analytics.

No real DB, no network. Uses the same module-stub pattern as test_guard_savings.py.

Strategy: stub sqlalchemy entirely so func.count/case never touch real SA machinery,
stub ORM model modules so RunAnalyticsEvent attribute accesses are MagicMock, and
inject pre-built result rows directly via the db.query chain.
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

# Stub heavy / infrastructure modules before any app import
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
    clerk_secret_key=None,
    clerk_frontend_api=None,
    environment="test",
)
sys.modules["app.core.config"] = _cfg_stub
sys.modules["app.core.database"] = MagicMock()

# Stub sqlalchemy so func/case/Session used by analytics.py are all MagicMocks.
# This prevents real SA from trying to process our mock column objects.
_sa_mock = MagicMock()
sys.modules["sqlalchemy"] = _sa_mock
sys.modules["sqlalchemy.orm"] = MagicMock()


# _Col: a column-like sentinel that supports all Python comparison operators.
# Required because analytics.py evaluates expressions like:
#   RunAnalyticsEvent.created_at >= cutoff  (Python >= before .filter() is called)
#   RunAnalyticsEvent.workspace_id == ws_hash
# With plain MagicMock these raise TypeError because datetime.__ge__(MagicMock)
# returns NotImplemented and MagicMock.__ge__(datetime) also cannot satisfy it.
class _Col:
    """Lightweight column stub: every comparison operator returns a new _Col."""
    def __ge__(self, other): return _Col()
    def __le__(self, other): return _Col()
    def __gt__(self, other): return _Col()
    def __lt__(self, other): return _Col()
    def __eq__(self, other): return _Col()
    def __ne__(self, other): return _Col()
    def __hash__(self): return id(self)
    def desc(self): return _Col()
    def __call__(self, *a, **kw): return _Col()


class _ModelStub:
    """ORM model stub: attribute access always returns a _Col instance."""
    def __getattr__(self, name):
        return _Col()


# Stub ORM model modules
_rae_cls = _ModelStub()
_rae_mod = MagicMock()
_rae_mod.RunAnalyticsEvent = _rae_cls
sys.modules["app.models.run_analytics_event"] = _rae_mod

_ros_cls = _ModelStub()
_ros_mod = MagicMock()
_ros_mod.RunOnlineScore = _ros_cls
sys.modules["app.models.run_online_score"] = _ros_mod

# Stub app.core.auth — analytics.py imports get_user_id, require_permission etc.
# Use setdefault so the real module wins if test_require_permission.py loaded first.
sys.modules.setdefault("app.core.auth", MagicMock())

from app.routers.analytics import get_dora  # noqa: E402

# Restore sqlalchemy in sys.modules so later test files that need the real
# package can import it cleanly. Our router module is already compiled; the
# stub was only needed to survive the module-level import.
sys.modules.pop("sqlalchemy", None)
sys.modules.pop("sqlalchemy.orm", None)

_WS = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------

def _totals(total=10, succeeded=8, avg_duration=45000):
    r = types.SimpleNamespace()
    r.total = total
    r.succeeded = succeeded
    r.avg_duration = avg_duration
    return r


def _trigger_row(trigger_type="webhook", runs=8, succeeded=7):
    r = types.SimpleNamespace()
    r.trigger_type = trigger_type
    r.runs = runs
    r.succeeded = succeeded
    return r


def _make_query_mock(totals_row, trigger_rows):
    """
    Returns a db mock where:
    - first() returns totals_row  (used for the overall totals query)
    - all() returns trigger_rows  (used for the per-trigger group-by query)
    """
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.filter.return_value = q
    q.group_by.return_value = q
    q.first.return_value = totals_row
    q.all.return_value = trigger_rows
    return db


def _call_get_dora(db, days=30):
    """Call get_dora bypassing FastAPI Depends — inject mocks directly."""
    return get_dora(
        workspace_id=_WS,
        _perm="developer",
        db=db,
        days=days,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDeploymentFrequency:
    def test_deployment_frequency(self):
        db = _make_query_mock(_totals(total=10, succeeded=8), [])
        result = _call_get_dora(db, days=30)
        # 8 succeeded / 30 days
        assert abs(result.deployment_frequency - round(8 / 30, 4)) < 1e-9

    def test_deployment_frequency_seven_days(self):
        db = _make_query_mock(_totals(total=7, succeeded=7), [])
        result = _call_get_dora(db, days=7)
        assert abs(result.deployment_frequency - round(7 / 7, 4)) < 1e-9


class TestChangeFailureRate:
    def test_change_failure_rate(self):
        db = _make_query_mock(_totals(total=10, succeeded=8), [])
        result = _call_get_dora(db)
        # 2 failed / 10 total = 0.2
        assert abs(result.change_failure_rate - 0.2) < 1e-9

    def test_zero_runs_no_division_error(self):
        db = _make_query_mock(_totals(total=0, succeeded=0, avg_duration=None), [])
        result = _call_get_dora(db)
        assert result.change_failure_rate == 0.0

    def test_all_succeeded_zero_failure_rate(self):
        db = _make_query_mock(_totals(total=5, succeeded=5), [])
        result = _call_get_dora(db)
        assert result.change_failure_rate == 0.0


class TestAvgDuration:
    def test_avg_duration_ms_present(self):
        db = _make_query_mock(_totals(avg_duration=45000), [])
        result = _call_get_dora(db)
        assert result.avg_duration_ms == 45000.0

    def test_avg_duration_ms_none(self):
        db = _make_query_mock(_totals(avg_duration=None), [])
        result = _call_get_dora(db)
        assert result.avg_duration_ms is None


class TestByTriggerBreakdown:
    def test_by_trigger_breakdown(self):
        db = _make_query_mock(
            _totals(),
            [_trigger_row(trigger_type="webhook", runs=8, succeeded=7)],
        )
        result = _call_get_dora(db)
        assert "webhook" in result.by_trigger
        wh = result.by_trigger["webhook"]
        assert wh["runs"] == 8
        assert wh["succeeded"] == 7
        assert wh["failed"] == 1
        assert abs(wh["failure_rate"] - round(1 / 8, 4)) < 1e-9

    def test_by_trigger_multiple_types(self):
        db = _make_query_mock(
            _totals(total=12, succeeded=10),
            [
                _trigger_row("webhook", runs=8, succeeded=7),
                _trigger_row("schedule", runs=4, succeeded=3),
            ],
        )
        result = _call_get_dora(db)
        assert "webhook" in result.by_trigger
        assert "schedule" in result.by_trigger

    def test_by_trigger_zero_runs_no_division_error(self):
        db = _make_query_mock(
            _totals(),
            [_trigger_row(trigger_type="manual", runs=0, succeeded=0)],
        )
        result = _call_get_dora(db)
        assert result.by_trigger["manual"]["failure_rate"] == 0.0

    def test_empty_trigger_rows(self):
        db = _make_query_mock(_totals(), [])
        result = _call_get_dora(db)
        assert result.by_trigger == {}


class TestWindowDays:
    def test_window_days_reflected(self):
        db = _make_query_mock(_totals(), [])
        result = _call_get_dora(db, days=7)
        assert result.window_days == 7

    def test_window_days_default_thirty(self):
        db = _make_query_mock(_totals(), [])
        result = _call_get_dora(db, days=30)
        assert result.window_days == 30

    def test_total_runs_in_response(self):
        db = _make_query_mock(_totals(total=10, succeeded=8), [])
        result = _call_get_dora(db)
        assert result.total_runs == 10
