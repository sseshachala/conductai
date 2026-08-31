"""Cross-tab pubsub smoke test (#1480 PR 14) — two subscribers on the same
session channel both receive a single published event.

The whole reason the design chose Redis pub/sub for fan-out was cross-tab
support 'comes free': every tab opens its own SSE connection, both
subscribe to `chan:session:<id>`, one PUBLISH → every subscriber gets a
message. This test proves the primitive works so we can trust the
architectural claim without a browser.

Auto-skips when Redis isn't reachable — same fixture pattern as the
other integration tests.
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


class _Disconnect:
    def __init__(self) -> None:
        self.value = False

    async def __call__(self) -> bool:
        return self.value


async def _next_data_frame(gen) -> dict:
    async for frame in gen:
        if not frame or frame.startswith(":"):
            continue
        for line in frame.split("\n"):
            if line.startswith("data: "):
                return json.loads(line[6:])
    raise AssertionError("generator ended without yielding a data frame")


@pytest.mark.asyncio
async def test_two_subscribers_on_same_session_both_receive_event() -> None:
    """Cross-tab: same user, two Lens tabs → two SSE connections →
    ONE publish should fan out to both."""
    sid = str(uuid.uuid4())
    r = redis.from_url(settings.redis_url, decode_responses=True)

    d1 = _Disconnect()
    d2 = _Disconnect()
    tab1 = _stream_events(sid, None, d1)
    tab2 = _stream_events(sid, None, d2)

    # Start both readers before publishing so the SUBSCRIBE inside each
    # generator has actually attached.
    reader1 = asyncio.create_task(_next_data_frame(tab1))
    reader2 = asyncio.create_task(_next_data_frame(tab2))
    await asyncio.sleep(0.25)

    entry_id = publish_session_event(
        sid, "action.confirmed",
        entity={"type": "approval", "id": "approval-xyz"},
        payload={"status": "approved"},
    )
    assert entry_id

    try:
        envelope1, envelope2 = await asyncio.wait_for(
            asyncio.gather(reader1, reader2), timeout=3.0,
        )
        # Both tabs got the same frame with the same stream id.
        assert envelope1["id"] == entry_id
        assert envelope2["id"] == entry_id
        assert envelope1["type"] == "action.confirmed"
        assert envelope2["type"] == "action.confirmed"
        assert envelope1["entity"] == {"type": "approval", "id": "approval-xyz"}
        assert envelope2["entity"] == {"type": "approval", "id": "approval-xyz"}
    finally:
        d1.value = True
        d2.value = True
        for gen in (tab1, tab2):
            try:
                await asyncio.wait_for(gen.aclose(), timeout=2.0)
            except (asyncio.TimeoutError, StopAsyncIteration):
                pass
        try:
            r.delete(_stream_key(sid))
        except Exception:
            pass
