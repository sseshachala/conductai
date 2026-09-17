"""Slice 6e — cache invalidation bus.

Redis pub/sub channel that carries invalidation events between workers.
Consumers (auth cache, effective-policy cache, budget ledger) subscribe
to event kinds relevant to their state and refresh proactively when
messages arrive.

Non-goal: this is NOT a correctness mechanism. Correctness of every
consumer cache comes from two independent guarantees:

1. **Version fencing on read.** Every cached entry carries a version
   number. Consumers check the entry against a monotonically-
   increasing source of truth (DB row version, generation counter,
   revision UUID) before returning the cached value. A stale entry
   is discarded on read even if no invalidation event arrived.

2. **Bounded refresh interval.** Every consumer periodically refreshes
   its state independent of the bus. If the bus is offline or a
   message is dropped, the worst case is a stale value served for
   up to ``refresh_interval`` seconds.

The bus is a *fast-path* optimization — it lets consumers refresh in
milliseconds instead of waiting the full refresh interval. Losing a
message is not a correctness bug; it's a temporary latency regression
on the invalidation.

Kill switch: ``INVALIDATION_BUS_ENABLED=false`` disables the bus.
Publish is a no-op and subscribers never fire. Consumers must remain
correct under this mode (i.e. version fencing + bounded refresh alone
must guarantee correctness — the bus only speeds up refresh).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Awaitable, Callable

import structlog

log = structlog.get_logger()

_CHANNEL_DEFAULT = "conduct.invalidation"

EventHandler = Callable[[dict], Awaitable[None]]


def _enabled() -> bool:
    """Kill switch checked each publish/subscribe call so ops can flip
    at runtime without restarting workers."""
    return os.environ.get("INVALIDATION_BUS_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )


class InvalidationBus:
    """Redis pub/sub wrapper. One instance per worker.

    Callers publish invalidation events via ``publish(kind, key, version)``.
    Callers subscribe to specific kinds via ``subscribe(kinds, handler)``.

    Reconnects on disconnect with exponential backoff (1s → 30s cap).
    Handler exceptions are logged and swallowed — a broken handler
    must not tear down the bus.
    """

    def __init__(
        self,
        redis_url: str | None = None,
        *,
        channel: str = _CHANNEL_DEFAULT,
        initial_backoff_seconds: float = 1.0,
        max_backoff_seconds: float = 30.0,
        publish_timeout_seconds: float = 0.5,
    ) -> None:
        self._redis_url = redis_url or os.environ.get("REDIS_URL", "redis://localhost:6379")
        self._channel = channel
        self._initial_backoff = initial_backoff_seconds
        self._max_backoff = max_backoff_seconds
        self._publish_timeout = publish_timeout_seconds
        self._client = None  # lazy — avoid connecting on import
        self._handlers: dict[str, list[EventHandler]] = {}
        self._sub_task: asyncio.Task | None = None
        self._events_published = 0
        self._events_received = 0
        self._publish_failures = 0
        self._reconnects = 0
        self._connected = False

    def _get_client(self):
        if self._client is None:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def publish(self, kind: str, key: str, version: int) -> None:
        """Fire-and-forget publish. Never raises to caller.

        A publish failure is recorded in ``publish_failures`` and
        logged. Consumers still refresh via their bounded-refresh
        path, so a lost publish is a latency regression, not a
        correctness bug.
        """
        if not _enabled():
            return
        try:
            payload = json.dumps({
                "kind": kind,
                "key": key,
                "version": version,
                "ts": time.time(),
            })
            client = self._get_client()
            # Bounded wait: a stalled Redis must not hold up the
            # caller. ``asyncio.wait_for`` cancels the pending publish
            # if it doesn't complete inside the timeout.
            await asyncio.wait_for(
                client.publish(self._channel, payload),
                timeout=self._publish_timeout,
            )
            self._events_published += 1
        except asyncio.TimeoutError:
            self._publish_failures += 1
            log.warning(
                "invalidation_bus.publish_timeout",
                kind=kind,
                key=key,
                timeout_seconds=self._publish_timeout,
            )
        except Exception as e:  # noqa: BLE001
            self._publish_failures += 1
            log.warning(
                "invalidation_bus.publish_failed",
                kind=kind,
                key=key,
                err=str(e),
            )

    def subscribe(self, kinds: list[str], handler: EventHandler) -> None:
        """Register an async handler for the given event kinds.

        Handler must be **idempotent** — it may be called multiple
        times for the same event across the bus and the periodic
        refresh path. Handler exceptions are logged and swallowed.
        """
        for kind in kinds:
            self._handlers.setdefault(kind, []).append(handler)

    async def start(self) -> None:
        """Start the background subscriber loop. Safe to call multiple
        times — no-op if already running."""
        if not _enabled() or self._sub_task is not None:
            return
        self._sub_task = asyncio.create_task(
            self._subscriber_loop(),
            name="invalidation_bus.subscriber",
        )

    async def stop(self) -> None:
        """Cancel the subscriber loop. Called from FastAPI shutdown."""
        if self._sub_task is not None:
            self._sub_task.cancel()
            try:
                await self._sub_task
            except (asyncio.CancelledError, Exception):
                pass
            self._sub_task = None
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass

    async def _subscriber_loop(self) -> None:
        """Long-running task: subscribe to Redis, dispatch messages to
        registered handlers, reconnect on disconnect.

        Reconnect strategy: exponential backoff starting at 1s, capped
        at 30s. Reset to 1s after a successful subscribe (not per-
        message, so a flapping connection doesn't peg the retry rate).

        Missed events during disconnected windows are NOT replayed —
        the bus is a fast-refresh signal only. Consumers rely on their
        own bounded-refresh path to recover.
        """
        backoff = self._initial_backoff
        while True:
            pubsub = None
            try:
                client = self._get_client()
                pubsub = client.pubsub()
                await pubsub.subscribe(self._channel)
                self._connected = True
                backoff = self._initial_backoff
                log.info(
                    "invalidation_bus.subscribed",
                    channel=self._channel,
                    handlers=list(self._handlers.keys()),
                )
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    self._events_received += 1
                    raw = message.get("data")
                    try:
                        event = json.loads(raw)
                    except Exception:
                        log.warning(
                            "invalidation_bus.malformed_event",
                            raw=str(raw)[:200],
                        )
                        continue
                    kind = event.get("kind")
                    if not kind:
                        continue
                    for handler in self._handlers.get(kind, []):
                        try:
                            await handler(event)
                        except Exception as e:  # noqa: BLE001
                            log.warning(
                                "invalidation_bus.handler_failed",
                                kind=kind,
                                err=str(e),
                            )
            except asyncio.CancelledError:
                self._connected = False
                if pubsub is not None:
                    try:
                        await pubsub.aclose()
                    except Exception:
                        pass
                raise
            except Exception as e:  # noqa: BLE001
                self._connected = False
                self._reconnects += 1
                log.warning(
                    "invalidation_bus.disconnected",
                    err=str(e),
                    retry_in_seconds=backoff,
                )
                if pubsub is not None:
                    try:
                        await pubsub.aclose()
                    except Exception:
                        pass
                await asyncio.sleep(backoff)
                backoff = min(self._max_backoff, backoff * 2)

    def stats(self) -> dict:
        return {
            "enabled": _enabled(),
            "connected": self._connected,
            "events_published": self._events_published,
            "events_received": self._events_received,
            "publish_failures": self._publish_failures,
            "reconnects": self._reconnects,
            "kinds": sorted(self._handlers.keys()),
            "handler_count": sum(len(h) for h in self._handlers.values()),
        }


_INSTANCE: InvalidationBus | None = None


def get_bus() -> InvalidationBus:
    """Return the process-global bus instance. Lazy — the Redis
    connection is not created until the first publish/subscribe."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = InvalidationBus()
    return _INSTANCE


def reset_bus_for_tests() -> None:
    """Test hook: wipe the global instance so per-test bus state
    doesn't leak."""
    global _INSTANCE
    _INSTANCE = None
