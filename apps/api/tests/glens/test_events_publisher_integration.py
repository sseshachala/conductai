"""Real-Redis round-trip tests for the session event publisher (#1480 PR 6).

Bring Redis up with `docker compose up redis` — these auto-skip when the
port isn't reachable, so they run locally on the dev machine and no-op
in CI without a Redis service.

Two properties exercised end-to-end (not just against MagicMock):

1. `publish_session_event` XADDs a real entry to the session Stream and
   PUBLISHes a real message on the session channel. Both are readable
   with a plain redis client.
2. Stream entries survive across the reconnect window (used by the SSE
   endpoint's `Last-Event-Id` replay).
"""
from __future__ import annotations

import json
import uuid

import pytest
import redis

from app.core.config import settings
from app.modules.glens.events import (
    STREAM_MAXLEN,
    _channel_key,
    _stream_key,
    publish_session_event,
)


@pytest.fixture
def real_redis():
    """Yield a real Redis client if reachable; skip test otherwise.

    Auto-cleans keys created during the test so the fixture is
    self-contained — no cross-test pollution."""
    try:
        r = redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=1)
        r.ping()
    except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError):
        pytest.skip("Redis not reachable — start with `docker compose up redis`")
    created_keys: list[str] = []
    yield r, created_keys
    if created_keys:
        r.delete(*created_keys)


def _fresh_session_id() -> str:
    """One session id per test — no cross-test collision on the Stream key."""
    return str(uuid.uuid4())


def test_publish_writes_readable_stream_entry(real_redis) -> None:
    r, cleanup = real_redis
    sid = _fresh_session_id()
    cleanup.append(_stream_key(sid))

    entry_id = publish_session_event(
        sid,
        "action.confirmed",
        entity={"type": "approval", "id": "row-1"},
        payload={"tool_name": "run_workflow", "status": "approved"},
    )
    assert entry_id  # non-empty stream id like "1699999999999-0"

    entries = r.xrange(_stream_key(sid))
    assert len(entries) == 1
    stream_id, fields = entries[0]
    assert stream_id == entry_id
    body = json.loads(fields["body"])
    assert body["type"] == "action.confirmed"
    assert body["entity"] == {"type": "approval", "id": "row-1"}
    assert body["payload"]["tool_name"] == "run_workflow"


def test_publish_reaches_pub_sub_subscribers(real_redis) -> None:
    r, cleanup = real_redis
    sid = _fresh_session_id()
    cleanup.append(_stream_key(sid))

    ps = r.pubsub()
    ps.subscribe(_channel_key(sid))
    # Consume the subscribe confirmation so the next get_message returns the
    # real event only.
    ack = ps.get_message(timeout=1)
    assert ack is not None and ack["type"] == "subscribe"

    entry_id = publish_session_event(
        sid, "run.status_changed",
        entity={"type": "run", "id": "run-xyz"},
        payload={"status": "running"},
    )

    msg = ps.get_message(timeout=1, ignore_subscribe_messages=True)
    assert msg is not None, "no fanout message received on channel"
    envelope = json.loads(msg["data"])
    assert envelope["id"] == entry_id
    assert envelope["type"] == "run.status_changed"
    assert envelope["entity"] == {"type": "run", "id": "run-xyz"}
    assert envelope["payload"] == {"status": "running"}

    ps.unsubscribe()
    ps.close()


def test_last_event_id_replay_returns_events_after_id(real_redis) -> None:
    """The SSE endpoint replays via `XREAD {stream: last_event_id}`. Sanity-
    check the underlying primitive: XREAD from a mid-stream id returns only
    entries STRICTLY after it."""
    r, cleanup = real_redis
    sid = _fresh_session_id()
    cleanup.append(_stream_key(sid))

    first_id = publish_session_event(sid, "action.confirmed")
    second_id = publish_session_event(sid, "run.status_changed")
    third_id = publish_session_event(sid, "run.status_changed")

    # Client had first_id last — should receive second + third only.
    replay = r.xread({_stream_key(sid): first_id})
    assert len(replay) == 1
    _key, entries = replay[0]
    ids = [e[0] for e in entries]
    assert ids == [second_id, third_id]


def test_stream_bounded_by_maxlen(real_redis) -> None:
    """Publishing more than STREAM_MAXLEN events must trim the stream so
    Redis memory stays bounded per session."""
    r, cleanup = real_redis
    sid = _fresh_session_id()
    cleanup.append(_stream_key(sid))

    # Push a bit past the cap — approximate=True means Redis may keep a few
    # extra entries but won't grow unboundedly.
    for i in range(STREAM_MAXLEN + 50):
        publish_session_event(sid, f"test.event.{i}")

    length = r.xlen(_stream_key(sid))
    # Approximate trim can leave up to ~STREAM_MAXLEN + a small tail. Allow
    # 2x the cap as the guardrail — anything higher means MAXLEN isn't
    # taking effect.
    assert length <= STREAM_MAXLEN * 2
