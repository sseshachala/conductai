"""Slice 6e — versioned-cache primitive for consumers of the invalidation bus.

Correctness contract every consumer must uphold:

1. **Version fencing.** Every cached entry carries a version number
   monotonically bound to a source of truth (DB row version, generation
   counter, revision UUID). ``VersionedCache.get()`` returns the cached
   value only if the entry's version is >= any minimum the caller
   requires.

2. **Bounded refresh.** Every entry has an age. If the age exceeds
   ``refresh_interval_seconds`` the entry is considered stale on read
   and the caller must refetch from the source of truth. This is the
   belt against missed invalidation events — worst-case staleness is
   bounded by the refresh interval, not by the availability of the
   invalidation bus.

3. **Single-flight refresh.** When multiple callers race on a cold key,
   only one refetches; the others wait. Thundering-herd guard.

This is a primitive, not a full cache. Consumers wrap their specific
source function around it (e.g. "resolve auth for token X",
"materialized effective policy for workspace Y") and register with
the invalidation bus.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Generic, TypeVar

import structlog

log = structlog.get_logger()

_T = TypeVar("_T")

FetchFn = Callable[[str], "Awaitable[tuple[Any, int]]"]  # (value, version)


@dataclass
class _Entry:
    value: Any
    version: int
    fetched_at: float


class VersionedCache(Generic[_T]):
    """Small typed cache with version + bounded-refresh + single-flight.

    Usage:

        async def _fetch(key: str) -> tuple[Value, int]:
            row = await db_read(key)
            return row.data, row.version

        cache = VersionedCache(fetch=_fetch, refresh_interval_seconds=60)
        value = await cache.get("workspace-1")

        # On invalidation event:
        cache.invalidate("workspace-1")

        # To force a version floor:
        value = await cache.get("workspace-1", min_version=42)

    Idempotent invalidations are safe — invalidating an already-absent
    key is a no-op.
    """

    def __init__(
        self,
        *,
        fetch: FetchFn,
        refresh_interval_seconds: float,
        max_entries: int = 10_000,
    ) -> None:
        if refresh_interval_seconds <= 0:
            raise ValueError("refresh_interval_seconds must be > 0")
        self._fetch = fetch
        self._refresh = refresh_interval_seconds
        self._max = max_entries
        self._entries: dict[str, _Entry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._hits = 0
        self._misses = 0
        self._stale_evictions = 0
        self._invalidations = 0

    def _stale(self, entry: _Entry) -> bool:
        return (time.monotonic() - entry.fetched_at) >= self._refresh

    def _key_lock(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock

    async def get(self, key: str, *, min_version: int | None = None) -> Any:
        """Return the cached value or refetch if missing/stale/below
        min_version. Only one refetch runs per key at a time.

        min_version=None → any cached-and-fresh entry is fine.
        min_version=N → the returned value's version must be >= N.
        """
        entry = self._entries.get(key)
        if (
            entry is not None
            and not self._stale(entry)
            and (min_version is None or entry.version >= min_version)
        ):
            self._hits += 1
            return entry.value
        self._misses += 1
        # Single-flight: only one coroutine refetches per key.
        async with self._key_lock(key):
            # Recheck after acquiring the lock — the winner may have
            # already populated the entry.
            entry = self._entries.get(key)
            if (
                entry is not None
                and not self._stale(entry)
                and (min_version is None or entry.version >= min_version)
            ):
                return entry.value
            value, version = await self._fetch(key)
            self._entries[key] = _Entry(
                value=value,
                version=version,
                fetched_at=time.monotonic(),
            )
            # Simple cap eviction — drop oldest fetched when over max.
            if len(self._entries) > self._max:
                oldest = min(self._entries.items(), key=lambda kv: kv[1].fetched_at)[0]
                self._entries.pop(oldest, None)
                self._locks.pop(oldest, None)
                self._stale_evictions += 1
            return value

    def invalidate(self, key: str) -> None:
        """Drop the entry for a key. Next get refetches. Safe to call
        for absent keys."""
        if self._entries.pop(key, None) is not None:
            self._invalidations += 1
        # Keep the lock — a concurrent refetch might be in flight and
        # popping the lock here would leak locks under contention.

    def invalidate_all(self) -> None:
        """Drop every entry. Used on massive events (e.g. workspace
        policy rebuild)."""
        n = len(self._entries)
        self._entries.clear()
        # Keep locks — same reasoning as invalidate().
        self._invalidations += n

    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "size": len(self._entries),
            "max": self._max,
            "refresh_interval_seconds": self._refresh,
            "hits": self._hits,
            "misses": self._misses,
            "invalidations": self._invalidations,
            "stale_evictions": self._stale_evictions,
            "hit_rate_bp": (10_000 * self._hits) // total if total else 0,
        }
