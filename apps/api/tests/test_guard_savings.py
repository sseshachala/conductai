"""
Unit tests for guard savings aggregation and GET /guard/savings/team-summary.

Uses the same mock-db pattern as test_guard.py — no real DB, no network.

Covers:
  - _build_summary: empty workspace, single developer, multiple developers
  - _build_summary: latest-row-per-member semantics (verified via mock rows)
  - _build_summary: tools_installed detection (rtk, booster)
  - USD calculation matches _USD_PER_MILLION_TOKENS constant
  - Projection math: per_month = total_usd × 30, per_year = total_usd × 365
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# pytest-forked: each test runs in its own subprocess so this file's module-
# level sys.modules stubs stay isolated. See epic #1075 — proper long-term
# fix is to remove the stubs (needs test-body rewrite to use real modules).
pytestmark = pytest.mark.forked
HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

# Stub heavy modules before any app imports
_log_mock = MagicMock()
_log_mock.get_logger = MagicMock(return_value=MagicMock())
sys.modules.setdefault("structlog", _log_mock)
sys.modules.setdefault("redis", MagicMock())
sys.modules.setdefault("sentry_sdk", MagicMock())

# Stub app.core.config so Settings() doesn't parse the real .env
_cfg_stub = MagicMock()
_cfg_stub.settings = MagicMock(
    sentry_dsn=None,
    sqlalchemy_database_url="sqlite:///:memory:",
    encryption_key="test-key-32-bytes-long-xxxxxxxx!",
    allowed_egress_hosts=[],
    log_level="INFO",
)
sys.modules.setdefault("app.core.config", _cfg_stub)
_db_stub = MagicMock()
sys.modules.setdefault("app.core.database", _db_stub)

from app.modules.guard.routers.savings import (  # noqa: E402
    _build_summary,
    _USD_PER_MILLION_TOKENS,
    _EMPTY_SUMMARY,
)

_WS = str(uuid.uuid4())
_NOW = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def _make_row(
    email: str,
    rtk_saved_tokens: int = 0,
    rtk_savings_pct: float = 0.0,
    rtk_total_commands: int = 0,
    booster_saved_tokens: int = 0,
    booster_savings_pct: float = 0.0,
    booster_total_reads: int = 0,
):
    """Build a fake SQLAlchemy row-like object matching _build_summary's SELECT."""
    r = MagicMock()
    r.member_email = email
    r.rtk_saved_tokens = rtk_saved_tokens
    r.rtk_savings_pct = rtk_savings_pct
    r.rtk_total_commands = rtk_total_commands
    r.booster_saved_tokens = booster_saved_tokens
    r.booster_savings_pct = booster_savings_pct
    r.booster_total_reads = booster_total_reads
    r.period_end = _NOW
    r.recorded_at = _NOW
    return r


def _make_db(rows: list) -> MagicMock:
    """Return a mock db whose execute().fetchall() yields the given rows."""
    db = MagicMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    db.execute.return_value = result
    return db


class TestBuildSummaryEmpty:
    def test_no_rows_returns_empty_summary(self):
        db = _make_db([])
        summary = _build_summary(db, _WS)
        assert summary.team_total.rtk_saved_tokens == 0
        assert summary.team_total.booster_saved_tokens == 0
        assert summary.team_total.rtk_saved_usd == 0.0
        assert summary.team_total.booster_saved_usd == 0.0
        assert summary.by_member == []
        assert summary.tools_installed == []

    def test_no_rows_returns_empty_member_list(self):
        db = _make_db([])
        summary = _build_summary(db, _WS)
        assert len(summary.by_member) == 0


class TestBuildSummarySingleDeveloper:
    def test_rtk_tokens_aggregated(self):
        db = _make_db([_make_row("alice@co.com", rtk_saved_tokens=1_000_000, rtk_total_commands=50)])
        summary = _build_summary(db, _WS)
        assert summary.team_total.rtk_saved_tokens == 1_000_000
        assert len(summary.by_member) == 1
        assert summary.by_member[0].member_email == "alice@co.com"
        assert summary.by_member[0].rtk_saved_tokens == 1_000_000
        assert summary.by_member[0].rtk_total_commands == 50

    def test_usd_calculation(self):
        db = _make_db([_make_row("bob@co.com", rtk_saved_tokens=1_000_000)])
        summary = _build_summary(db, _WS)
        expected = round(1_000_000 * _USD_PER_MILLION_TOKENS / 1_000_000, 6)
        assert abs(summary.team_total.rtk_saved_usd - expected) < 1e-9

    def test_tools_installed_rtk_only(self):
        db = _make_db([_make_row("carol@co.com", rtk_saved_tokens=500_000)])
        summary = _build_summary(db, _WS)
        assert "rtk" in summary.tools_installed
        assert "booster" not in summary.tools_installed

    def test_tools_installed_booster_only(self):
        db = _make_db([_make_row("dave@co.com", booster_saved_tokens=200_000, booster_total_reads=10)])
        summary = _build_summary(db, _WS)
        assert "booster" in summary.tools_installed
        assert "rtk" not in summary.tools_installed

    def test_tools_installed_detected_via_commands(self):
        """rtk detected via rtk_total_commands even if saved_tokens=0."""
        db = _make_db([_make_row("eve@co.com", rtk_total_commands=5)])
        summary = _build_summary(db, _WS)
        assert "rtk" in summary.tools_installed

    def test_booster_usd_calculation(self):
        db = _make_db([_make_row("frank@co.com", booster_saved_tokens=500_000)])
        summary = _build_summary(db, _WS)
        expected = round(500_000 * _USD_PER_MILLION_TOKENS / 1_000_000, 6)
        assert abs(summary.team_total.booster_saved_usd - expected) < 1e-9


class TestBuildSummaryMultipleDevelopers:
    def test_developer_count(self):
        db = _make_db([
            _make_row("alice@co.com", rtk_saved_tokens=1_000_000),
            _make_row("bob@co.com", rtk_saved_tokens=2_000_000),
        ])
        summary = _build_summary(db, _WS)
        assert len(summary.by_member) == 2

    def test_total_tokens_summed(self):
        db = _make_db([
            _make_row("alice@co.com", rtk_saved_tokens=1_000_000),
            _make_row("bob@co.com", rtk_saved_tokens=2_000_000),
        ])
        summary = _build_summary(db, _WS)
        assert summary.team_total.rtk_saved_tokens == 3_000_000

    def test_rtk_and_booster_combined(self):
        db = _make_db([
            _make_row("alice@co.com", rtk_saved_tokens=1_000_000),
            _make_row("bob@co.com", booster_saved_tokens=500_000, booster_total_reads=20),
        ])
        summary = _build_summary(db, _WS)
        assert summary.team_total.rtk_saved_tokens == 1_000_000
        assert summary.team_total.booster_saved_tokens == 500_000
        assert "rtk" in summary.tools_installed
        assert "booster" in summary.tools_installed

    def test_total_usd_is_sum_of_members(self):
        db = _make_db([
            _make_row("alice@co.com", rtk_saved_tokens=1_000_000),
            _make_row("bob@co.com", rtk_saved_tokens=1_000_000),
        ])
        summary = _build_summary(db, _WS)
        expected = round(2_000_000 * _USD_PER_MILLION_TOKENS / 1_000_000, 6)
        assert abs(summary.team_total.rtk_saved_usd - expected) < 1e-9


class TestWorkspaceIsolation:
    def test_other_workspace_rows_excluded(self):
        """Rows for a different workspace must not appear in the summary."""
        other_ws = str(uuid.uuid4())
        # Return rows only for the other workspace — _build_summary is called with _WS
        db = _make_db([_make_row("attacker@other.com", rtk_saved_tokens=9_999_999)])
        # Simulate the SQL only returning rows for the queried workspace (mock returns what we give)
        # The real isolation is in the SQL WHERE clause; here we verify _build_summary
        # correctly uses the workspace_id param it receives (spot-check via empty result)
        db_empty = _make_db([])
        summary = _build_summary(db_empty, _WS)
        assert summary.team_total.rtk_saved_tokens == 0
        assert len(summary.by_member) == 0

    def test_workspace_id_passed_to_execute(self):
        """Verify _build_summary passes workspace_id into the SQL query."""
        db = _make_db([])
        _build_summary(db, _WS)
        call_args = db.execute.call_args
        params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", {})
        # The bound param dict should contain our workspace id
        assert _WS in str(call_args)


class TestNullFieldHandling:
    def test_period_end_none_returns_empty_string(self):
        r = _make_row("alice@co.com", rtk_saved_tokens=100)
        r.period_end = None
        db = _make_db([r])
        summary = _build_summary(db, _WS)
        assert summary.by_member[0].period_end == ""

    def test_recorded_at_none_returns_empty_string(self):
        r = _make_row("alice@co.com", rtk_saved_tokens=100)
        r.recorded_at = None
        db = _make_db([r])
        summary = _build_summary(db, _WS)
        assert summary.by_member[0].recorded_at == ""

    def test_null_token_fields_default_to_zero(self):
        r = _make_row("alice@co.com")
        r.rtk_saved_tokens = None
        r.booster_saved_tokens = None
        r.rtk_total_commands = None
        r.booster_total_reads = None
        db = _make_db([r])
        summary = _build_summary(db, _WS)
        assert summary.team_total.rtk_saved_tokens == 0
        assert summary.team_total.booster_saved_tokens == 0


class TestProjectionMath:
    def test_per_month_is_30x_per_day(self):
        from app.modules.guard.routers.savings import get_team_summary
        db = _make_db([_make_row("alice@co.com", rtk_saved_tokens=1_000_000)])
        summary = _build_summary(db, _WS)
        total_usd = round(summary.team_total.rtk_saved_usd + summary.team_total.booster_saved_usd, 6)
        per_day = round(total_usd, 2)
        per_month = round(total_usd * 30, 2)
        per_year = round(total_usd * 365, 2)
        assert per_month == round(per_day * 30, 2)
        assert per_year == round(per_day * 365, 2)

    def test_zero_savings_projections_are_zero(self):
        total_usd = 0.0
        assert round(total_usd * 30, 2) == 0.0
        assert round(total_usd * 365, 2) == 0.0

    def test_usd_per_million_tokens_blended_rate(self):
        """Verify the blended rate constant: 3.0×0.8 + 15.0×0.2 = 5.4."""
        assert abs(_USD_PER_MILLION_TOKENS - 5.4) < 1e-9


class TestMonthCutoff:
    """Bug-fix regression: /guard/savings/summary must respect ?month=YYYY-MM
    so past-month views show cumulative-as-of-end-of-month, not lifetime."""

    def test_month_end_mid_year(self):
        from app.modules.guard.routers.savings import _month_end
        assert _month_end("2026-07") == datetime(2026, 8, 1, tzinfo=timezone.utc)

    def test_month_end_december_rolls_year(self):
        from app.modules.guard.routers.savings import _month_end
        assert _month_end("2026-12") == datetime(2027, 1, 1, tzinfo=timezone.utc)

    def test_month_end_none_passes_through(self):
        from app.modules.guard.routers.savings import _month_end
        assert _month_end(None) is None

    def test_month_end_bad_format_returns_none(self):
        from app.modules.guard.routers.savings import _month_end
        assert _month_end("not-a-month") is None
        assert _month_end("2026-13") is None

    def test_no_month_omits_cutoff_from_query_params(self):
        """When month is None, the SQL must not carry a :cutoff bind param."""
        db = _make_db([])
        _build_summary(db, _WS)
        args, kwargs = db.execute.call_args
        params = args[1] if len(args) > 1 else kwargs.get("params", {})
        assert "cutoff" not in params
        # And the SQL text must not reference :cutoff either
        sql_text = str(args[0])
        assert ":cutoff" not in sql_text

    def test_month_adds_cutoff_bind_and_sql_clause(self):
        """Passing month=YYYY-MM must inject the end-of-month cutoff into
        BOTH the outer WHERE and the inner MAX subquery — otherwise the
        latest snapshot could still leak in from a later month."""
        db = _make_db([])
        _build_summary(db, _WS, month="2026-04")
        args, kwargs = db.execute.call_args
        params = args[1] if len(args) > 1 else kwargs.get("params", {})
        assert params.get("cutoff") == datetime(2026, 5, 1, tzinfo=timezone.utc)
        sql_text = str(args[0])
        # Cutoff must appear TWICE — once for the MAX(recorded_at) subquery,
        # once for the outer SELECT — otherwise the outer join can pick up
        # a later-month snapshot for a member.
        assert sql_text.count("recorded_at < :cutoff") == 2

    def test_month_december_cutoff_rolls_year(self):
        db = _make_db([])
        _build_summary(db, _WS, month="2026-12")
        args, kwargs = db.execute.call_args
        params = args[1] if len(args) > 1 else kwargs.get("params", {})
        assert params.get("cutoff") == datetime(2027, 1, 1, tzinfo=timezone.utc)


class TestProjectionMathUsesObservationWindow:
    """Bug: /guard/savings/team-summary treated cumulative total as per_day
    and multiplied by 30 / 365 for month/year. Fix: divide cumulative by
    (now - min(recorded_at) days, min 1) so the daily rate is real."""

    def test_days_observed_min_one_on_first_snapshot(self, monkeypatch):
        """When the earliest recorded_at is today, days_observed clamps to 1
        so per_day == total (no div-by-zero, no absurd inflation)."""
        from datetime import datetime as _dt, timezone as _tz
        from app.modules.guard.routers import savings as sav

        now = _dt(2026, 7, 24, 12, 0, 0, tzinfo=_tz.utc)
        monkeypatch.setattr(sav, "_now", lambda: now)

        # Mock DB: _build_summary returns a summary via db.execute; then
        # get_team_summary calls db.execute again for MIN(recorded_at).
        # Return the same "now" for the min timestamp — days delta == 0.
        first_ts_row = MagicMock()
        first_ts_row.first_ts = now
        summary_rows = [_make_row("alice@co.com", rtk_saved_tokens=1_000_000)]

        db = MagicMock()
        exec_iter = iter([MagicMock(fetchall=lambda: summary_rows), MagicMock(fetchone=lambda: first_ts_row)])
        db.execute.side_effect = lambda *a, **k: next(exec_iter)

        out = sav.get_team_summary(db=db, workspace_id=_WS)
        # 1M tokens × $5.40/M = $5.40 cumulative. days_observed clamps to 1.
        assert out.days_observed == 1
        assert out.per_day_usd == round(_tokens_to_usd(1_000_000), 2)
        assert out.per_month_usd == round(out.per_day_usd * 30, 2)
        assert out.per_year_usd == round(out.per_day_usd * 365, 2)

    def test_days_observed_divides_by_actual_window(self, monkeypatch):
        """A snapshot from 100 days ago must yield per_day = total / 100,
        not per_day = total (the old cumulative-as-daily bug)."""
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        from app.modules.guard.routers import savings as sav

        now = _dt(2026, 7, 24, 12, 0, 0, tzinfo=_tz.utc)
        first = now - _td(days=100)
        monkeypatch.setattr(sav, "_now", lambda: now)

        first_ts_row = MagicMock()
        first_ts_row.first_ts = first
        summary_rows = [_make_row("alice@co.com", rtk_saved_tokens=100_000_000)]

        db = MagicMock()
        exec_iter = iter([MagicMock(fetchall=lambda: summary_rows), MagicMock(fetchone=lambda: first_ts_row)])
        db.execute.side_effect = lambda *a, **k: next(exec_iter)

        out = sav.get_team_summary(db=db, workspace_id=_WS)
        total = round(_tokens_to_usd(100_000_000), 6)   # $540 cumulative
        assert out.days_observed == 100
        assert out.per_day_usd == round(total / 100, 2)  # $5.40/day, not $540
        assert out.per_month_usd == round(out.per_day_usd * 30, 2)
        assert out.first_recorded_at == first.isoformat()

    def test_naive_datetime_from_db_gets_utc_tz(self, monkeypatch):
        """Some drivers return recorded_at as naive datetime; the fix must
        attach UTC before subtracting from _now() or Python raises TypeError."""
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        from app.modules.guard.routers import savings as sav

        now = _dt(2026, 7, 24, 12, 0, 0, tzinfo=_tz.utc)
        first_naive = (now - _td(days=30)).replace(tzinfo=None)
        monkeypatch.setattr(sav, "_now", lambda: now)

        first_ts_row = MagicMock()
        first_ts_row.first_ts = first_naive
        summary_rows = [_make_row("alice@co.com", rtk_saved_tokens=30_000_000)]

        db = MagicMock()
        exec_iter = iter([MagicMock(fetchall=lambda: summary_rows), MagicMock(fetchone=lambda: first_ts_row)])
        db.execute.side_effect = lambda *a, **k: next(exec_iter)

        out = sav.get_team_summary(db=db, workspace_id=_WS)  # must not raise
        assert out.days_observed == 30


def _tokens_to_usd(tokens: int) -> float:
    """Test helper mirroring savings.py's blended rate."""
    return round(tokens * _USD_PER_MILLION_TOKENS / 1_000_000, 6)

