"""Race-free trial cap reservation self-check (epic #1587 A4)."""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

HERE = Path(__file__).resolve()
APPS_API = HERE.parent.parent
if str(APPS_API) not in sys.path:
    sys.path.insert(0, str(APPS_API))


def _redis_is_reachable() -> bool:
    try:
        import redis
        from app.core.config import settings
        r = redis.from_url(settings.redis_url, socket_connect_timeout=1)
        r.ping()
        return True
    except Exception:
        return False


if not _redis_is_reachable():
    pytest.skip("Redis unreachable", allow_module_level=True)


from app.modules.guard.trial_upstream import (  # noqa: E402
    TRIAL_DAILY_CAP,
    _redis_client,
    try_reserve_trial_slot,
)


@pytest.fixture()
def ws_and_aid():
    ws = str(uuid.uuid4())
    aid = str(uuid.uuid4())
    yield ws, aid
    # Clean up today's cap key so a repeated test doesn't leak.
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    _redis_client().delete(f"guard:trial:cap:{ws}:{aid}:{day}")


def test_first_reservation_passes(ws_and_aid):
    ws, aid = ws_and_aid
    assert try_reserve_trial_slot(ws, aid) is True


def test_cap_is_atomic_at_exactly_TRIAL_DAILY_CAP(ws_and_aid):
    """Reserve exactly TRIAL_DAILY_CAP times — all True; the next one False."""
    ws, aid = ws_and_aid
    for _ in range(TRIAL_DAILY_CAP):
        assert try_reserve_trial_slot(ws, aid) is True
    assert try_reserve_trial_slot(ws, aid) is False


def test_falls_open_when_redis_unreachable(ws_and_aid):
    """A Redis outage must not defeat trial availability."""
    ws, aid = ws_and_aid

    class _Boom:
        def pipeline(self):
            raise ConnectionError("simulated redis outage")

    with patch("app.modules.guard.trial_upstream._redis_client", return_value=_Boom()):
        # Any number of calls all pass — the fallback is fail-open.
        assert try_reserve_trial_slot(ws, aid) is True
        assert try_reserve_trial_slot(ws, aid) is True


def test_separate_workspaces_do_not_share_a_bucket(ws_and_aid):
    """One workspace hitting cap must not block another."""
    ws1, aid1 = ws_and_aid
    ws2, aid2 = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        for _ in range(TRIAL_DAILY_CAP):
            assert try_reserve_trial_slot(ws1, aid1) is True
        assert try_reserve_trial_slot(ws1, aid1) is False
        # Different workspace — first call still passes.
        assert try_reserve_trial_slot(ws2, aid2) is True
    finally:
        day = datetime.now(timezone.utc).strftime("%Y%m%d")
        _redis_client().delete(f"guard:trial:cap:{ws2}:{aid2}:{day}")


def test_key_expires_after_window(ws_and_aid):
    """The Redis key must have a TTL so buckets don't accumulate forever."""
    ws, aid = ws_and_aid
    try_reserve_trial_slot(ws, aid)
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    ttl = _redis_client().ttl(f"guard:trial:cap:{ws}:{aid}:{day}")
    # TTL should be positive and no larger than the 24h window.
    assert 0 < ttl <= 24 * 3600
