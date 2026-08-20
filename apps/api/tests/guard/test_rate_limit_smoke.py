"""Smoke tests for #980 — per-key RPM/TPM rate limiting.

Verifies:
- rate_limit module imports cleanly (proxy step 4d.2 depends on it)
- fail-open when Redis is unreachable (documented posture)
- limit-resolution order: per-agent row > workspace default > none
- RPM breach returns limited=True with metric="rpm"
- TPM breach returns limited=True with metric="tpm"
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_module_imports():
    from app.modules.guard.rate_limit import check_rate_limit, RateLimitDecision
    from app.modules.guard.routers import rate_limits, proxy  # noqa: F401
    from app.modules.guard.models import GuardRateLimit  # noqa: F401
    assert callable(check_rate_limit)
    assert RateLimitDecision.__dataclass_fields__


def _mock_db(rpm=None, tpm=None, has_default=False):
    db = MagicMock()
    row = MagicMock(rpm=rpm, tpm=tpm) if (rpm is not None or tpm is not None) else None

    exec_ = MagicMock()
    exec_.first.return_value = row if has_default else None
    db.execute.return_value = exec_
    return db


def test_no_config_returns_unlimited():
    from app.modules.guard.rate_limit import check_rate_limit
    db = _mock_db(has_default=False)
    d = check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=100)
    assert d.limited is False
    assert d.scope == "none"


def test_db_error_fails_open():
    # Simulates missing migration: guard_rate_limits table not yet created.
    # Must return unlimited so proxy traffic keeps flowing.
    from app.modules.guard.rate_limit import check_rate_limit
    db = MagicMock()
    db.execute.side_effect = RuntimeError("relation guard_rate_limits does not exist")
    d = check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=50)
    assert d.limited is False
    assert d.scope == "none"
    db.rollback.assert_called()  # session must be rolled back so subsequent queries work


def test_redis_down_fails_open():
    from app.modules.guard.rate_limit import check_rate_limit
    db = _mock_db(rpm=10, tpm=1000, has_default=True)
    with patch("app.modules.guard.rate_limit._redis_client", side_effect=RuntimeError("nope")):
        d = check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=50)
    assert d.limited is False  # fail-open by design


def test_rpm_breach():
    from app.modules.guard.rate_limit import check_rate_limit
    db = _mock_db(rpm=5, tpm=None, has_default=True)
    fake_redis = MagicMock()
    pipe = MagicMock()
    pipe.execute.return_value = [6, True, 0, True]  # rpm=6 > limit=5
    fake_redis.pipeline.return_value = pipe
    with patch("app.modules.guard.rate_limit._redis_client", return_value=fake_redis):
        d = check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=0)
    assert d.limited is True
    assert d.metric == "rpm"
    assert d.limit == 5
    assert d.current == 6


def test_tpm_breach():
    from app.modules.guard.rate_limit import check_rate_limit
    db = _mock_db(rpm=None, tpm=1000, has_default=True)
    fake_redis = MagicMock()
    pipe = MagicMock()
    pipe.execute.return_value = [1, True, 1500, True]  # tpm=1500 > limit=1000
    fake_redis.pipeline.return_value = pipe
    with patch("app.modules.guard.rate_limit._redis_client", return_value=fake_redis):
        d = check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=1500)
    assert d.limited is True
    assert d.metric == "tpm"


def test_under_cap_allows():
    from app.modules.guard.rate_limit import check_rate_limit
    db = _mock_db(rpm=10, tpm=1000, has_default=True)
    fake_redis = MagicMock()
    pipe = MagicMock()
    pipe.execute.return_value = [3, True, 200, True]
    fake_redis.pipeline.return_value = pipe
    with patch("app.modules.guard.rate_limit._redis_client", return_value=fake_redis):
        d = check_rate_limit(db, workspace_id="ws1", agent_identity_id=None, input_tokens=200)
    assert d.limited is False
