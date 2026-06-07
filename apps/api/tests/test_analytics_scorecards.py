"""
Unit tests for get_scorecards in app.routers.analytics.

No real DB, no network. Uses the same module-stub pattern as test_guard_savings.py.

Strategy: stub sqlalchemy entirely so func/case/Session are all MagicMocks,
stub ORM model modules, and inject result rows directly via db.query chain.
"""
from __future__ import annotations

import os
import sys
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

# Stub sqlalchemy so func/case/Session used by analytics.py are all MagicMocks
_sa_mock = MagicMock()
sys.modules["sqlalchemy"] = _sa_mock
sys.modules["sqlalchemy.orm"] = MagicMock()


# _Col: column-like sentinel supporting Python comparison operators.
# analytics.py evaluates RunAnalyticsEvent.created_at >= cutoff as a Python
# expression before passing it to .filter(). Plain MagicMock raises TypeError
# here because datetime.__ge__(MagicMock) returns NotImplemented.
class _Col:
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

sys.modules.setdefault("app.core.auth", MagicMock())

from app.routers.analytics import get_scorecards  # noqa: E402

# Restore sqlalchemy so later test files that need the real package can import it.
sys.modules.pop("sqlalchemy", None)
sys.modules.pop("sqlalchemy.orm", None)

_WS = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------

def _make_score_row(
    slug,
    grade,
    pct,
    mechanical_score=30,
    mechanical_max=40,
    judge_score=0,
    judge_max=0,
    judge_used=False,
):
    r = MagicMock()
    r.slug = slug
    r.grade = grade
    r.pct = pct
    r.mechanical_score = mechanical_score
    r.mechanical_max = mechanical_max
    r.judge_score = judge_score
    r.judge_max = judge_max
    r.judge_used = judge_used
    return r


def _make_db(rows):
    db = MagicMock()
    q = MagicMock()
    db.query.return_value = q
    q.join.return_value = q
    q.filter.return_value = q
    q.all.return_value = rows
    return db


def _call_get_scorecards(db, days=30):
    return get_scorecards(
        workspace_id=_WS,
        _perm="developer",
        db=db,
        days=days,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmptyResult:
    def test_empty_returns_empty_list(self):
        db = _make_db([])
        result = _call_get_scorecards(db)
        assert result == []


class TestSingleSlugAggregation:
    def test_single_slug_aggregated(self):
        rows = [
            _make_score_row("pr_reviewer", "A", 90),
            _make_score_row("pr_reviewer", "B", 80),
        ]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        assert len(result) == 1
        sc = result[0]
        assert sc.playbook_slug == "pr_reviewer"
        assert sc.run_count == 2
        assert abs(sc.avg_pct - 85.0) < 1e-9

    def test_single_slug_grade_from_avg_pct(self):
        rows = [
            _make_score_row("pr_reviewer", "A", 90),
            _make_score_row("pr_reviewer", "B", 80),
        ]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        # avg_pct=85.0 → grade B (>=80, <90)
        assert result[0].grade == "B"


class TestGradeDistribution:
    def test_grade_dist_counts(self):
        rows = [
            _make_score_row("deploy", "A", 95),
            _make_score_row("deploy", "A", 92),
            _make_score_row("deploy", "B", 85),
            _make_score_row("deploy", "C", 75),
        ]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        dist = result[0].grade_dist
        assert dist["A"] == 2
        assert dist["B"] == 1
        assert dist["C"] == 1
        assert dist["D"] == 0
        assert dist["F"] == 0

    def test_grade_dist_has_all_keys(self):
        rows = [_make_score_row("solo", "A", 95)]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        dist = result[0].grade_dist
        for key in ("A", "B", "C", "D", "F"):
            assert key in dist


class TestGradeThresholds:
    def test_avg_pct_to_grade_A(self):
        rows = [_make_score_row("wf", "A", 95)]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        assert result[0].grade == "A"

    def test_avg_pct_to_grade_B(self):
        rows = [_make_score_row("wf", "B", 85)]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        assert result[0].grade == "B"

    def test_avg_pct_to_grade_C(self):
        rows = [_make_score_row("wf", "C", 75)]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        assert result[0].grade == "C"

    def test_avg_pct_to_grade_D(self):
        rows = [_make_score_row("wf", "D", 65)]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        assert result[0].grade == "D"

    def test_avg_pct_to_grade_F(self):
        rows = [_make_score_row("wf", "F", 50)]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        assert result[0].grade == "F"


class TestMultipleSlugs:
    def test_multiple_slugs(self):
        rows = [
            _make_score_row("pr_reviewer", "A", 92),
            _make_score_row("deploy_check", "B", 82),
        ]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        assert len(result) == 2
        slugs = {sc.playbook_slug for sc in result}
        assert "pr_reviewer" in slugs
        assert "deploy_check" in slugs


class TestJudgeAveraging:
    def test_judge_avg_when_unused(self):
        rows = [
            _make_score_row("wf", "A", 90, judge_score=0, judge_max=0, judge_used=False),
            _make_score_row("wf", "A", 90, judge_score=0, judge_max=0, judge_used=False),
        ]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        assert result[0].avg_judge == 0.0

    def test_judge_avg_when_used(self):
        rows = [
            _make_score_row("wf", "A", 90, judge_score=80, judge_max=100, judge_used=True),
        ]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        assert abs(result[0].avg_judge - 80.0) < 1e-6

    def test_judge_avg_mixed_used_and_unused(self):
        # Only judge_used=True entries count toward avg_judge
        rows = [
            _make_score_row("wf", "A", 90, judge_score=60, judge_max=100, judge_used=True),
            _make_score_row("wf", "B", 80, judge_score=0, judge_max=0, judge_used=False),
        ]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        # Only the first row contributes: 60/100 * 100 = 60.0
        assert abs(result[0].avg_judge - 60.0) < 1e-6

    def test_judge_avg_multiple_used_entries(self):
        rows = [
            _make_score_row("wf", "A", 95, judge_score=90, judge_max=100, judge_used=True),
            _make_score_row("wf", "A", 90, judge_score=70, judge_max=100, judge_used=True),
        ]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        # (90 + 70) / (100 + 100) * 100 = 80.0
        assert abs(result[0].avg_judge - 80.0) < 1e-6


class TestSortOrder:
    def test_sorted_by_avg_pct_desc(self):
        rows = [
            _make_score_row("low_scorer", "C", 70),
            _make_score_row("high_scorer", "A", 95),
            _make_score_row("mid_scorer", "B", 82),
        ]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        assert result[0].playbook_slug == "high_scorer"
        assert result[1].playbook_slug == "mid_scorer"
        assert result[2].playbook_slug == "low_scorer"

    def test_sorted_descending_two_slugs(self):
        rows = [
            _make_score_row("slug_a", "B", 80),
            _make_score_row("slug_b", "A", 95),
        ]
        db = _make_db(rows)
        result = _call_get_scorecards(db)
        assert result[0].avg_pct > result[1].avg_pct
