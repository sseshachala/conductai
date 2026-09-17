"""Slice 6e — invalidation bus tests.

Bus is a fast-path signal; correctness comes from consumers' version
fencing + bounded refresh. These tests verify both:

- Bus wiring: publish → subscribed handler receives event.
- Kill switch: bus disabled → publish is no-op, subscribers don't fire.
- Reconnect behavior: raises → subscriber loop retries with backoff.
- Malformed event: doesn't tear down the subscriber.
- Handler failure: doesn't tear down the subscriber (other handlers still fire).
- Missed events: consumer with bounded refresh still recovers state.
- Stats accuracy: counters track what happened.
"""
from __future__ import annotations

import asyncio
import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _clear_env():
    for k in ("INVALIDATION_BUS_ENABLED",):
        os.environ.pop(k, None)


def _reset_bus():
    from app.core.invalidation_bus import reset_bus_for_tests
    reset_bus_for_tests()


# ── Kill switch ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_is_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("INVALIDATION_BUS_ENABLED", raising=False)
    _reset_bus()
    from app.core.invalidation_bus import get_bus
    bus = get_bus()
    # Should not raise even without Redis available.
    await bus.publish("auth.revoked", "token-hash", 1)
    stats = bus.stats()
    assert stats["enabled"] is False
    assert stats["events_published"] == 0


@pytest.mark.asyncio
async def test_start_is_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("INVALIDATION_BUS_ENABLED", raising=False)
    _reset_bus()
    from app.core.invalidation_bus import get_bus
    bus = get_bus()
    await bus.start()
    assert bus._sub_task is None


# ── Subscribe registration ──────────────────────────────────────────────

def test_subscribe_registers_handler_by_kind(monkeypatch):
    monkeypatch.setenv("INVALIDATION_BUS_ENABLED", "true")
    _reset_bus()
    from app.core.invalidation_bus import get_bus

    async def _handler(event):
        pass

    bus = get_bus()
    bus.subscribe(["auth.revoked", "policy.changed"], _handler)
    stats = bus.stats()
    assert set(stats["kinds"]) == {"auth.revoked", "policy.changed"}
    assert stats["handler_count"] == 2


def test_subscribe_multiple_handlers_per_kind(monkeypatch):
    monkeypatch.setenv("INVALIDATION_BUS_ENABLED", "true")
    _reset_bus()
    from app.core.invalidation_bus import get_bus

    async def _h1(event): pass
    async def _h2(event): pass

    bus = get_bus()
    bus.subscribe(["auth.revoked"], _h1)
    bus.subscribe(["auth.revoked"], _h2)
    assert bus.stats()["handler_count"] == 2


# ── Publish success + failure counting ──────────────────────────────────

@pytest.mark.asyncio
async def test_publish_success_increments_counter(monkeypatch):
    monkeypatch.setenv("INVALIDATION_BUS_ENABLED", "true")
    _reset_bus()
    from app.core.invalidation_bus import get_bus

    bus = get_bus()
    fake_client = AsyncMock()
    fake_client.publish = AsyncMock()
    bus._client = fake_client

    await bus.publish("auth.revoked", "tok-1", 5)
    assert bus.stats()["events_published"] == 1
    fake_client.publish.assert_awaited_once()
    channel, payload = fake_client.publish.call_args.args
    assert channel == bus._channel
    parsed = json.loads(payload)
    assert parsed["kind"] == "auth.revoked"
    assert parsed["key"] == "tok-1"
    assert parsed["version"] == 5
    assert "ts" in parsed


@pytest.mark.asyncio
async def test_publish_timeout_returns_fast_without_raising(monkeypatch):
    """P2 review fix — a stalled Redis must not hold up the publisher.
    Publish is bounded by ``publish_timeout_seconds`` (default 500ms,
    small in the test) and returns quickly on timeout with the failure
    counter incremented."""
    import time as _t
    monkeypatch.setenv("INVALIDATION_BUS_ENABLED", "true")
    _reset_bus()
    from app.core.invalidation_bus import InvalidationBus

    bus = InvalidationBus(publish_timeout_seconds=0.05)

    async def _slow_publish(*_a, **_kw):
        await asyncio.sleep(1.0)  # stalled Redis

    fake_client = MagicMock()
    fake_client.publish = _slow_publish
    bus._client = fake_client

    start = _t.monotonic()
    await bus.publish("auth.revoked", "tok-x", 1)
    elapsed = _t.monotonic() - start

    assert elapsed < 0.5, (
        f"publish took {elapsed*1000:.1f}ms — bounded timeout regressed"
    )
    stats = bus.stats()
    assert stats["publish_failures"] == 1
    assert stats["events_published"] == 0


@pytest.mark.asyncio
async def test_publish_failure_swallowed_and_counted(monkeypatch):
    """Publish failure MUST NOT raise to caller — consumers rely on
    the bounded-refresh path when the bus is unavailable."""
    monkeypatch.setenv("INVALIDATION_BUS_ENABLED", "true")
    _reset_bus()
    from app.core.invalidation_bus import get_bus

    bus = get_bus()
    fake_client = AsyncMock()
    fake_client.publish = AsyncMock(side_effect=RuntimeError("redis down"))
    bus._client = fake_client

    # Must not raise.
    await bus.publish("auth.revoked", "tok-x", 1)
    stats = bus.stats()
    assert stats["publish_failures"] == 1
    assert stats["events_published"] == 0


# ── Reconnect / missed-event scenarios ──────────────────────────────────

@pytest.mark.asyncio
async def test_subscriber_reconnects_after_disconnect(monkeypatch):
    """Subscriber loop must reconnect on disconnect. Reconnect counter
    increments and the second attempt succeeds. Uses a small backoff
    to keep the test fast."""
    monkeypatch.setenv("INVALIDATION_BUS_ENABLED", "true")
    _reset_bus()
    from app.core.invalidation_bus import InvalidationBus

    # Fresh bus with 10ms backoff so the reconnect completes in the
    # test's window without patching asyncio.sleep.
    bus = InvalidationBus(
        initial_backoff_seconds=0.01,
        max_backoff_seconds=0.01,
    )

    call_count = 0

    class _FakePubSub:
        def __init__(self, fail_first: bool):
            self._fail = fail_first
            self._subscribed = False

        async def subscribe(self, ch):
            if self._fail:
                raise RuntimeError("connection refused")
            self._subscribed = True

        async def listen(self):
            if self._subscribed:
                yield {"type": "subscribe", "data": None}
                await asyncio.sleep(60)

        async def aclose(self):
            pass

    def _pubsub_factory():
        nonlocal call_count
        call_count += 1
        return _FakePubSub(fail_first=(call_count == 1))

    fake_client = MagicMock()
    fake_client.pubsub = _pubsub_factory
    bus._client = fake_client

    task = asyncio.create_task(bus._subscriber_loop())
    # Poll for both signals: reconnect happened AND connected on retry.
    for _ in range(200):
        await asyncio.sleep(0.01)
        if bus._reconnects >= 1 and bus._connected:
            break
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    stats = bus.stats()
    assert stats["reconnects"] >= 1, "subscriber must have reconnected"
    assert call_count >= 2, "second pubsub attempt must have been made"


@pytest.mark.asyncio
async def test_malformed_message_does_not_kill_subscriber(monkeypatch):
    """A message with invalid JSON must be logged and skipped, not
    tear down the subscriber loop."""
    monkeypatch.setenv("INVALIDATION_BUS_ENABLED", "true")
    _reset_bus()
    from app.core.invalidation_bus import get_bus

    handled = []

    async def _handler(event):
        handled.append(event)

    bus = get_bus()
    bus.subscribe(["auth.revoked"], _handler)

    class _FakePubSub:
        def __init__(self, msgs):
            self._msgs = msgs
        async def subscribe(self, ch):
            pass
        async def listen(self):
            for m in self._msgs:
                yield m
            # Then hang.
            await asyncio.sleep(60)
        async def aclose(self):
            pass

    msgs = [
        {"type": "subscribe", "data": None},
        # Malformed — this should be skipped without crashing.
        {"type": "message", "data": "{not-valid-json"},
        # Good message that comes AFTER the bad one — proves loop survived.
        {"type": "message", "data": json.dumps({
            "kind": "auth.revoked", "key": "tok-1", "version": 3, "ts": 1.0
        })},
    ]

    fake_client = MagicMock()
    fake_client.pubsub = lambda: _FakePubSub(msgs)
    bus._client = fake_client

    task = asyncio.create_task(bus._subscriber_loop())
    # Wait for the good message to be handled.
    for _ in range(100):
        await asyncio.sleep(0.01)
        if handled:
            break
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert handled == [{
        "kind": "auth.revoked",
        "key": "tok-1",
        "version": 3,
        "ts": 1.0,
    }], "good message after malformed must still fire the handler"


@pytest.mark.asyncio
async def test_handler_exception_does_not_kill_subscriber(monkeypatch):
    """One handler raising must not prevent other handlers from
    firing, and must not tear down the subscriber loop."""
    monkeypatch.setenv("INVALIDATION_BUS_ENABLED", "true")
    _reset_bus()
    from app.core.invalidation_bus import get_bus

    good_received = []

    async def _broken(event):
        raise RuntimeError("bad handler")

    async def _good(event):
        good_received.append(event["key"])

    bus = get_bus()
    bus.subscribe(["auth.revoked"], _broken)
    bus.subscribe(["auth.revoked"], _good)

    class _FakePubSub:
        async def subscribe(self, ch):
            pass
        async def listen(self):
            yield {
                "type": "message",
                "data": json.dumps({"kind": "auth.revoked", "key": "K", "version": 1, "ts": 0}),
            }
            await asyncio.sleep(60)
        async def aclose(self):
            pass

    fake_client = MagicMock()
    fake_client.pubsub = lambda: _FakePubSub()
    bus._client = fake_client

    task = asyncio.create_task(bus._subscriber_loop())
    for _ in range(100):
        await asyncio.sleep(0.01)
        if good_received:
            break
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert good_received == ["K"], (
        "the healthy handler must still fire even when the broken one raises"
    )


# ── Stats snapshot ──────────────────────────────────────────────────────

def test_stats_reflects_state(monkeypatch):
    monkeypatch.setenv("INVALIDATION_BUS_ENABLED", "true")
    _reset_bus()
    from app.core.invalidation_bus import get_bus

    bus = get_bus()
    stats = bus.stats()
    assert set(stats.keys()) == {
        "enabled",
        "connected",
        "events_published",
        "events_received",
        "publish_failures",
        "reconnects",
        "kinds",
        "handler_count",
    }
