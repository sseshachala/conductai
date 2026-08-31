"""Real-Redis round-trip test of the SSE async generator (#1480 PR 6.5).

We bypass HTTP entirely — httpx's ASGITransport buffers streaming
responses (well-known FastAPI+httpx quirk), so a full endpoint test
hangs. Instead we drive `_stream_events()` directly and verify the
pub/sub → yield pipeline.

Coverage:
- Live pub/sub: publish an event, the next yielded frame carries it
- Last-Event-Id replay: connect with a prior stream id, replay frames
  strictly after that id BEFORE any live event

Auto-skips when Redis unreachable (same fixture as
test_events_publisher_integration.py).
"""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest
import redis

from app.core.config import settings
from app.modules.glens.events import _stream_key, publish_session_event
from app.modules.glens.routers.session_stream import _stream_events


def _redis_reachable() -> bool:
    try:
        redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=1).ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_reachable(),
    reason="Redis not reachable — start with `docker compose up redis`",
)


@pytest.fixture
def redis_cleanup():
    """Yield a callback that registers keys to delete after the test."""
    r = redis.from_url(settings.redis_url, decode_responses=True)
    keys: list[str] = []
    yield keys.append
    if keys:
        r.delete(*keys)


class _Disconnect:
    """Awaitable stub for FastAPI's request.is_disconnected — flip .value
    to unwedge the generator's while-loop from tests."""
    def __init__(self) -> None:
        self.value = False

    async def __call__(self) -> bool:
        return self.value


async def _first_data_frame(gen) -> dict:
    """Pull frames from the async generator until we find a `data:` frame
    (skipping keepalive comments). Returns the parsed JSON envelope."""
    async for frame in gen:
        if not frame or frame.startswith(":"):
            continue
        for line in frame.split("\n"):
            if line.startswith("data: "):
                return json.loads(line[6:])
    raise AssertionError("generator ended without yielding a data frame")


@pytest.mark.asyncio
async def test_generator_yields_frame_from_live_publish(redis_cleanup) -> None:
    """publish_session_event → subscribe queue → _stream_events yields
    the frame with the right envelope."""
    sid = str(uuid.uuid4())
    redis_cleanup(_stream_key(sid))

    disconnect = _Disconnect()
    gen = _stream_events(sid, None, disconnect)

    # Kick the generator once to let it SUBSCRIBE before we publish. The
    # first `async for` step advances the generator into the subscribe +
    # into the pub/sub poll — at that point the subscriber is live.
    reader = asyncio.create_task(_first_data_frame(gen))
    await asyncio.sleep(0.2)

    entry_id = publish_session_event(
        sid, "action.confirmed",
        entity={"type": "approval", "id": "approval-xyz"},
        payload={"status": "approved"},
    )
    assert entry_id  # publish succeeded

    envelope = await asyncio.wait_for(reader, timeout=3.0)
    assert envelope["id"] == entry_id
    assert envelope["type"] == "action.confirmed"
    assert envelope["entity"] == {"type": "approval", "id": "approval-xyz"}
    assert envelope["payload"] == {"status": "approved"}

    disconnect.value = True
    # Let the generator observe the disconnect and clean up.
    try:
        await asyncio.wait_for(gen.aclose(), timeout=2.0)
    except (asyncio.TimeoutError, StopAsyncIteration):
        pass


@pytest.mark.asyncio
async def test_generator_replays_from_last_event_id_before_live(redis_cleanup) -> None:
    """When connecting with Last-Event-Id, the generator MUST yield the
    Stream entries AFTER that id first, before it starts forwarding
    live pub/sub messages."""
    sid = str(uuid.uuid4())
    redis_cleanup(_stream_key(sid))

    first_id = publish_session_event(sid, "action.confirmed", payload={"n": 1})
    second_id = publish_session_event(sid, "run.status_changed", payload={"n": 2})
    third_id = publish_session_event(sid, "run.status_changed", payload={"n": 3})
    assert first_id and second_id and third_id

    disconnect = _Disconnect()
    gen = _stream_events(sid, first_id, disconnect)

    replayed: list[dict] = []
    async for frame in gen:
        if not frame or frame.startswith(":"):
            continue
        for line in frame.split("\n"):
            if line.startswith("data: "):
                replayed.append(json.loads(line[6:]))
        # Replay of two entries done — flip disconnect to end the generator.
        if len(replayed) >= 2:
            disconnect.value = True
            break

    assert [e["id"] for e in replayed] == [second_id, third_id]
    assert [e["payload"]["n"] for e in replayed] == [2, 3]

    try:
        await asyncio.wait_for(gen.aclose(), timeout=2.0)
    except (asyncio.TimeoutError, StopAsyncIteration):
        pass
