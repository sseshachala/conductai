"""Alert dispatch storm guards + worker checks (#2142, #2524)."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://" + "test:test" + "@localhost:5432/test_marshal")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("ENCRYPTION_KEY", "test-key-32-bytes-long-xxxxxxxx!")

from app.modules.guard import alert_dispatch, alert_worker


class FakeRedis:
    def __init__(self):
        self.kv, self.hashes = {}, {}

    def set(self, key, val, nx=False, ex=None):
        if nx and key in self.kv:
            return None
        self.kv[key] = val
        return True

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[field] = value

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def expire(self, *a, **k):
        pass


def _chan(ctype="webhook", threshold=None, window=300, ref="https://93.184.216.34/h"):
    return SimpleNamespace(id=uuid.uuid4(), channel_type=ctype, channel_ref=ref,
                           threshold_per_min=threshold, dedupe_window_sec=window,
                           integration_id=None)


def _run(monkeypatch, channels, r, **kw):
    sent = []
    monkeypatch.setattr(alert_dispatch, "_matching_channels", lambda *a, **k: channels)
    from app.modules.guard.routers import events_notify
    monkeypatch.setattr(events_notify, "_fanout_webhook", lambda chs, payload: sent.append((chs, payload)))
    n = alert_dispatch.dispatch_alert(
        MagicMock(), uuid.uuid4(), "gateway", "upstream_5xx", title="t", message="m",
        source_id="p1", client=r, **kw)
    return n, sent


def test_dispatch_dedupes_within_window(monkeypatch):
    r, ch = FakeRedis(), [_chan()]
    assert _run(monkeypatch, ch, r)[0] == 1
    assert _run(monkeypatch, ch, r)[0] == 0


def test_dispatch_zero_window_never_dedupes(monkeypatch):
    r, ch = FakeRedis(), [_chan(window=0)]
    assert _run(monkeypatch, ch, r)[0] == 1
    assert _run(monkeypatch, ch, r)[0] == 1


def test_dispatch_threshold(monkeypatch):
    ch = [_chan(threshold=10)]
    assert _run(monkeypatch, ch, FakeRedis(), rate_per_min=9)[0] == 0
    assert _run(monkeypatch, ch, FakeRedis(), rate_per_min=10)[0] == 1
    assert _run(monkeypatch, ch, FakeRedis())[0] == 0  # unknown rate never satisfies a threshold


def test_dispatch_threshold_miss_does_not_consume_dedupe(monkeypatch):
    r, ch = FakeRedis(), [_chan(threshold=10)]
    assert _run(monkeypatch, ch, r, rate_per_min=1)[0] == 0
    assert _run(monkeypatch, ch, r, rate_per_min=50)[0] == 1


def test_dispatch_unknown_event_is_noop():
    assert alert_dispatch.dispatch_alert(
        MagicMock(), uuid.uuid4(), "gateway", "nope", title="t", message="m") == 0


def test_dispatch_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db down")
    monkeypatch.setattr(alert_dispatch, "_matching_channels", boom)
    assert alert_dispatch.dispatch_alert(
        MagicMock(), uuid.uuid4(), "gateway", "upstream_5xx", title="t", message="m") == 0


def test_webhook_payload_has_no_channel_url(monkeypatch):
    _, sent = _run(monkeypatch, [_chan()], FakeRedis())
    assert "93.184.216.34" not in json.dumps(sent[0][1])


# ── Feed transitions ────────────────────────────────────────────────────────

def _feed(r, ws, actor, last_pull):
    r.hset(f"audit_feed:status:{ws}", actor, json.dumps({
        "last_pull_at": last_pull.isoformat(), "cursor_ts": last_pull.isoformat(),
        "last_page_events": 1}))


def test_feed_alerts_once_on_stale_and_once_on_recovery(monkeypatch):
    ws, r = uuid.uuid4(), FakeRedis()
    calls = []
    monkeypatch.setattr(alert_worker, "_workspaces_with_channels", lambda db, st: [ws])
    monkeypatch.setattr(alert_worker, "dispatch_alert", lambda *a, **k: calls.append(k["details"]["state"]) or 1)
    now = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)

    _feed(r, ws, "splunk", now - timedelta(minutes=2))
    alert_worker.check_feed_alerts(MagicMock(), now=now, client=r)
    assert calls == []  # healthy, no alert

    _feed(r, ws, "splunk", now - timedelta(minutes=20))
    alert_worker.check_feed_alerts(MagicMock(), now=now, client=r)
    alert_worker.check_feed_alerts(MagicMock(), now=now + timedelta(minutes=1), client=r)
    alert_worker.check_feed_alerts(MagicMock(), now=now + timedelta(minutes=2), client=r)
    assert calls == ["stale"]  # once, no repeats

    later = now + timedelta(minutes=5)
    _feed(r, ws, "splunk", later - timedelta(minutes=1))
    alert_worker.check_feed_alerts(MagicMock(), now=later, client=r)
    alert_worker.check_feed_alerts(MagicMock(), now=later + timedelta(minutes=1), client=r)
    assert calls == ["stale", "ok"]


def test_feed_check_skips_when_redis_unavailable(monkeypatch):
    ws = uuid.uuid4()
    monkeypatch.setattr(alert_worker, "_workspaces_with_channels", lambda db, st: [ws])
    called = MagicMock()
    monkeypatch.setattr(alert_worker, "dispatch_alert", called)

    class Down(FakeRedis):
        def hgetall(self, key):
            raise ConnectionError("down")

    assert alert_worker.check_feed_alerts(MagicMock(), client=Down()) == 0
    called.assert_not_called()


# ── Gateway aggregation ─────────────────────────────────────────────────────

def test_gateway_check_dispatches_one_alert_per_profile_event(monkeypatch):
    ws = uuid.uuid4()
    monkeypatch.setattr(alert_worker, "_workspaces_with_channels", lambda db, st: [ws])
    monkeypatch.setattr(alert_worker, "gateway_event_counts",
                        lambda db, w, since: {("p1", "upstream_5xx"): 120, ("p2", "rate_limit_exceeded"): 3})
    seen = []
    monkeypatch.setattr(alert_worker, "dispatch_alert", lambda *a, **k: seen.append((k["source_id"], a[3], k["rate_per_min"])) or 1)
    assert alert_worker.check_gateway_alerts(MagicMock()) == 2
    assert seen == [("p1", "upstream_5xx", 120.0), ("p2", "rate_limit_exceeded", 3.0)]


def test_gateway_counts_query_compiles_for_postgres():
    from sqlalchemy.dialects import postgresql

    captured = {}

    class Q:
        def __init__(self, *cols):
            captured["cols"] = cols

        def filter(self, *c):
            captured["filter"] = c
            return self

        def group_by(self, *c):
            return self

        def all(self):
            return []

    db = MagicMock()
    db.query.side_effect = lambda *cols: Q(*cols)
    assert alert_worker.gateway_event_counts(db, uuid.uuid4(), datetime.now(timezone.utc)) == {}
    sql = str(captured["cols"][1].compile(dialect=postgresql.dialect()))
    assert " ~ " in sql
    assert "CASE" in sql
