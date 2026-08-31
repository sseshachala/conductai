"""Verify publish_session_event XADDs + PUBLISHes with the right shape.

Foundation test for #1480 SSE surface (PR 1). Real Redis not required —
publisher takes an injectable client so we assert on MagicMock calls.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

from app.modules.glens.events import (
    STREAM_MAXLEN,
    STREAM_TTL_SECONDS,
    publish_session_event,
)


_SESSION = "11111111-1111-1111-1111-111111111111"


def _mock_redis(entry_id: str = "1699999999999-0") -> MagicMock:
    r = MagicMock()
    r.xadd.return_value = entry_id
    return r


def test_publishes_stream_entry_with_bounded_maxlen() -> None:
    r = _mock_redis()
    publish_session_event(_SESSION, "action.confirmed", client=r)

    r.xadd.assert_called_once()
    args, kwargs = r.xadd.call_args
    assert args[0] == f"stream:session:{_SESSION}"
    assert kwargs["maxlen"] == STREAM_MAXLEN
    assert kwargs["approximate"] is True


def test_publishes_pub_sub_with_stream_id_envelope() -> None:
    r = _mock_redis(entry_id="1699999999999-0")
    publish_session_event(
        _SESSION,
        "action.confirmed",
        entity={"type": "approval", "id": "abc"},
        payload={"outcome": "ok"},
        client=r,
    )

    r.publish.assert_called_once()
    channel, raw = r.publish.call_args.args
    assert channel == f"chan:session:{_SESSION}"
    body = json.loads(raw)
    # Stream id envelope — clients use it for Last-Event-Id resume
    assert body["id"] == "1699999999999-0"
    assert body["type"] == "action.confirmed"
    assert body["entity"] == {"type": "approval", "id": "abc"}
    assert body["payload"] == {"outcome": "ok"}
    assert "at" in body


def test_returns_stream_id_for_use_as_sse_event_id() -> None:
    r = _mock_redis(entry_id="1699999999999-0")
    entry_id = publish_session_event(_SESSION, "run.completed", client=r)
    assert entry_id == "1699999999999-0"


def test_stream_ttl_refreshed_on_every_publish() -> None:
    r = _mock_redis()
    publish_session_event(_SESSION, "action.confirmed", client=r)
    r.expire.assert_called_once_with(f"stream:session:{_SESSION}", STREAM_TTL_SECONDS)


def test_optional_entity_and_payload_omitted_from_body() -> None:
    r = _mock_redis()
    publish_session_event(_SESSION, "session.closed", client=r)
    body = json.loads(r.publish.call_args.args[1])
    assert "entity" not in body
    assert "payload" not in body


def test_publish_is_fail_open_when_redis_errors() -> None:
    """A dropped SSE event must never fail the underlying business op.

    Publisher is called AFTER Confirm/Cancel/Decide has already committed.
    If Redis is down, the run is enqueued — the user just misses a live
    event. Returning empty string signals "no id" without raising.
    """
    r = MagicMock()
    r.xadd.side_effect = RuntimeError("redis down")
    entry_id = publish_session_event(_SESSION, "action.confirmed", client=r)
    assert entry_id == ""
    # Publish must NOT be attempted when xadd blew up (would fail too, and
    # the fanout envelope needs a real stream id anyway).
    r.publish.assert_not_called()


def test_uuid_session_id_accepted() -> None:
    import uuid

    r = _mock_redis()
    publish_session_event(uuid.UUID(_SESSION), "run.status_changed", client=r)
    assert r.xadd.call_args.args[0] == f"stream:session:{_SESSION}"


def test_fail_open_when_redis_from_url_itself_raises() -> None:
    """Regression test: earlier version constructed the Redis client OUTSIDE
    the try/except, so a mocked-to-raise `redis.from_url` (as used by
    executor lifecycle tests) blew past the fail-open handler and crashed
    the caller. Every failure mode inside publish_session_event MUST be
    swallowed."""
    from unittest.mock import patch

    with patch("app.modules.glens.events.redis.from_url", side_effect=RuntimeError("redis down")):
        entry_id = publish_session_event(_SESSION, "action.confirmed")
    assert entry_id == ""
