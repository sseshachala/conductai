"""Regression guard: SQLALCHEMY_MAX_OVERFLOW=0 must be honoured as a
hard cap (no burst capacity), not silently clamped to 1.

The reviewer flagged this on PR #2066: ``_pool_int`` clamped at
``max(1, int(raw))``, which turned an explicit request for a hard
cap into a soft cap of 1 extra connection. That defeats the whole
point of setting ``max_overflow=0``.
"""
from __future__ import annotations

import os
from unittest.mock import patch


def test_pool_int_pool_size_minimum_one():
    """``pool_size`` gets minimum=1 (default) — a zero-connection pool
    is nonsensical."""
    from app.core.database import _pool_int
    with patch.dict(os.environ, {"TEST_POOL_SIZE": "0"}):
        assert _pool_int("TEST_POOL_SIZE", 5) == 1


def test_pool_int_max_overflow_allows_zero():
    """``max_overflow=0`` is a legitimate config meaning ``no burst
    capacity, hard-cap at pool_size``. Must not be clamped to 1."""
    from app.core.database import _pool_int
    with patch.dict(os.environ, {"TEST_MAX_OVERFLOW": "0"}):
        assert _pool_int("TEST_MAX_OVERFLOW", 10, minimum=0) == 0


def test_pool_int_max_overflow_negative_clamped_to_zero():
    """Negative values clamp to ``minimum`` — should not be interpreted
    as ``unlimited``."""
    from app.core.database import _pool_int
    with patch.dict(os.environ, {"TEST_MAX_OVERFLOW": "-5"}):
        assert _pool_int("TEST_MAX_OVERFLOW", 10, minimum=0) == 0


def test_pool_int_max_overflow_positive():
    """Positive value passes through when >= minimum."""
    from app.core.database import _pool_int
    with patch.dict(os.environ, {"TEST_MAX_OVERFLOW": "20"}):
        assert _pool_int("TEST_MAX_OVERFLOW", 10, minimum=0) == 20


def test_pool_int_invalid_falls_back_to_default():
    """Non-integer input falls back to the passed default."""
    from app.core.database import _pool_int
    with patch.dict(os.environ, {"TEST_POOL_SIZE": "not-a-number"}):
        assert _pool_int("TEST_POOL_SIZE", 7) == 7


def test_pool_int_env_missing_falls_back_to_default():
    """Unset env falls back to the default."""
    from app.core.database import _pool_int
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("TEST_POOL_UNSET", None)
        assert _pool_int("TEST_POOL_UNSET", 3) == 3


def test_pool_int_source_uses_minimum_zero_for_max_overflow():
    """Source-level guard: the call site for max_overflow in
    ``database.py`` must pass ``minimum=0`` so a hard cap request is
    honoured. Reviewer's P2 on PR #2066.

    An end-to-end engine reload test would validate this behaviourally
    but ``importlib.reload`` on ``database`` corrupts every other
    test's ``SessionLocal`` reference — the reload creates a new
    engine instance that existing sessions don't know about. This
    source check is the safer form of the same guarantee."""
    from pathlib import Path
    src = Path(
        __file__
    ).resolve().parents[2].joinpath("app", "core", "database.py").read_text()
    assert '_pool_int("SQLALCHEMY_MAX_OVERFLOW"' in src, (
        "max_overflow env var wiring missing from database.py"
    )
    # The specific string that says "minimum=0" is next to the
    # max_overflow call. If it drifts, this catches it.
    assert "SQLALCHEMY_MAX_OVERFLOW\", 10, minimum=0" in src, (
        "max_overflow must be parsed with minimum=0 so SQLALCHEMY_"
        "MAX_OVERFLOW=0 hard-caps the pool. Reviewer's P2 on PR #2066."
    )
