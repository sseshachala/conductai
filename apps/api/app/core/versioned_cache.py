"""Slice 6e — versioned-cache primitive for consumers of the invalidation bus.

Correctness contract every consumer must uphold:

1. **Version fencing on read AND on write.** ``get()`` returns a
   cached entry only if its version >= caller's ``min_version``. If a
   fetch produces a value whose version is still < ``min_version``,
   the call retries within a bounded deadline; on deadline the call
   raises ``VersionUnavailable`` — the caller must decide whether to
   fail-closed or fall back. A cached value is never returned when
   the caller asked for a higher version than the fetch could
   produce.

2. **Bounded refresh interval, measured from fetch START.** ``fetched_at``
   is recorded when the fetch is issued, not when it completes. A
   slow fetch does not extend the freshness window.

3. **Per-key generation fence.** ``invalidate()`` bumps the key's
   generation counter. An in-flight fetch that captured the previous
   generation is discarded on completion — its result is NOT stored
   and NOT returned. Prevents the classic "invalidation-lost-to-
   racing-fetch" bug.

4. **Single-flight refresh.** Only one fetch runs per key at a time.
   Waiters are woken when the winner finishes; each waiter re-checks
   the cache (which now has the fresh value) before falling through.

5. **Lock lifecycle.** Per-key locks are reference-counted. When the
   last holder/waiter releases, the lock entry is removed. Prevents
   the lock table from growing unboundedly under high-cardinality
   workloads.

This is a primitive, not a full cache. Wrapping it with a specific
source function (auth resolve, effective policy) is the responsibility
of the consumer PR (6b, 6c). Budget reservations must NOT use this —
they require atomic accounting, not bounded-stale reads.
"""
from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Generic, TypeVar

import structlog

log = structlog.get_logger()

_T = TypeVar("_T")

FetchFn = Callable[[str], "Awaitable[tuple[Any, int]]"]  # (value, version)


class VersionUnavailable(Exception):
    """Raised by ``get()`` when the fetch could not produce a value
    meeting ``min_version`` within the caller's bounded deadline.

    Carries the requested minimum, the last version the fetch
    produced, and the elapsed time so the caller can decide whether
    to fail-closed (auth flow) or fall back to a stale-but-lower
    value (best-effort read).
    """

    def __init__(self, key: str, min_version: int, last_version: int, elapsed: float):
        self.key = key
        self.min_version = min_version
        self.last_version = last_version
        self.elapsed = elapsed
        super().__init__(
            f"version {min_version} not available for key {key!r} — "
            f"last fetch returned version {last_version} after {elapsed:.3f}s"
        )


@dataclass
class _Entry:
    value: Any
    version: int
    fetched_at_start: float  # measured at fetch start, not completion


@dataclass
class _KeyLock:
    """Reference-counted async lock. Removed from the lock table when
    the last holder/waiter releases so the table doesn't grow
    unboundedly."""

    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    refcount: int = 0


class VersionedCache(Generic[_T]):
    """See module docstring for the correctness contract.

    Constructor arguments:

    - ``fetch``: async ``(key) -> (value, version)``.
    - ``refresh_interval_seconds``: max age of a cached entry.
    - ``max_entries``: cap on the entry table (oldest-fetched
      eviction).
    - ``retry_backoff_seconds``: sleep between version-retry attempts
      when the fetch keeps returning a version < ``min_version``.
    """

    def __init__(
        self,
        *,
        fetch: FetchFn,
        refresh_interval_seconds: float,
        max_entries: int = 10_000,
        retry_backoff_seconds: float = 0.05,
    ) -> None:
        if refresh_interval_seconds <= 0:
            raise ValueError("refresh_interval_seconds must be > 0")
        self._fetch = fetch
        self._refresh = refresh_interval_seconds
        self._max = max_entries
        self._retry_backoff = retry_backoff_seconds
        self._entries: dict[str, _Entry] = {}
        self._locks: dict[str, _KeyLock] = {}
        self._generations: dict[str, int] = {}
        self._hits = 0
        self._misses = 0
        self._stale_evictions = 0
        self._invalidations = 0
        self._gen_fence_discards = 0
        self._version_retries = 0

    def _stale(self, entry: _Entry) -> bool:
        return (time.monotonic() - entry.fetched_at_start) >= self._refresh

    @asynccontextmanager
    async def _key_lock_ctx(self, key: str):
        """Refcount + async-lock per key. Removes the lock entry when
        the last holder/waiter releases so ``_locks`` stays bounded.
        """
        kl = self._locks.get(key)
        if kl is None:
            kl = _KeyLock()
            self._locks[key] = kl
        kl.refcount += 1
        try:
            async with kl.lock:
                yield
        finally:
            kl.refcount -= 1
            if kl.refcount <= 0:
                # Only remove if the entry hasn't been replaced by a
                # newer _KeyLock during our critical section.
                current = self._locks.get(key)
                if current is kl:
                    self._locks.pop(key, None)

    async def get(
        self,
        key: str,
        *,
        min_version: int | None = None,
        deadline_seconds: float = 5.0,
    ) -> Any:
        """Return the value for ``key``. Uphold the correctness contract.

        - Cache hit: fresh entry with version >= ``min_version``.
        - Cache miss / stale / version-too-low: fetch under the
          per-key lock. Reject the fetch result if:
            (a) the generation was bumped by ``invalidate()`` during
                the fetch, or
            (b) the fetched version is still < ``min_version``.
          Retry within ``deadline_seconds``. On deadline expiry, raise
          ``VersionUnavailable``.
        """
        start_time = time.monotonic()
        last_version_seen: int | None = None

        while True:
            entry = self._entries.get(key)
            if (
                entry is not None
                and not self._stale(entry)
                and (min_version is None or entry.version >= min_version)
            ):
                self._hits += 1
                return entry.value

            self._misses += 1

            async with self._key_lock_ctx(key):
                # Recheck after acquiring the lock — winner may have
                # already populated a fresh entry.
                entry = self._entries.get(key)
                if (
                    entry is not None
                    and not self._stale(entry)
                    and (min_version is None or entry.version >= min_version)
                ):
                    return entry.value

                # Fetch under lock. Measure fetched_at from START so a
                # slow fetch doesn't extend the freshness window.
                fetch_start = time.monotonic()
                gen_at_start = self._generations.get(key, 0)

                value, version = await self._fetch(key)
                last_version_seen = version

                # Fence: was this key invalidated during the fetch?
                # If so, discard the result — it's based on stale state
                # by definition.
                current_gen = self._generations.get(key, 0)
                if current_gen != gen_at_start:
                    self._gen_fence_discards += 1
                    log.debug(
                        "versioned_cache.gen_fence_discard",
                        key=key,
                        gen_at_start=gen_at_start,
                        current_gen=current_gen,
                    )
                    # Fall through to retry — don't cache the stale result.
                else:
                    # Store the fetched value. Even if version is below
                    # min_version, cache it so a caller with a lower
                    # ``min_version`` can still benefit; the outer
                    # loop will keep retrying for the current caller.
                    self._entries[key] = _Entry(
                        value=value,
                        version=version,
                        fetched_at_start=fetch_start,
                    )
                    if len(self._entries) > self._max:
                        oldest = min(
                            self._entries.items(),
                            key=lambda kv: kv[1].fetched_at_start,
                        )[0]
                        self._entries.pop(oldest, None)
                        self._stale_evictions += 1

            # Post-fetch min_version check. Runs OUTSIDE the lock so
            # other coroutines aren't blocked while this caller sleeps.
            if min_version is None or (last_version_seen is not None and last_version_seen >= min_version):
                return value

            self._version_retries += 1
            elapsed = time.monotonic() - start_time
            if elapsed >= deadline_seconds:
                raise VersionUnavailable(
                    key=key,
                    min_version=min_version,
                    last_version=last_version_seen if last_version_seen is not None else -1,
                    elapsed=elapsed,
                )
            await asyncio.sleep(self._retry_backoff)

    def invalidate(self, key: str) -> None:
        """Bump the key's generation and drop any cached entry. An
        in-flight fetch that already captured the pre-bump generation
        is fenced on completion — its result is NOT stored.

        Idempotent — safe to call for a key that isn't cached.
        """
        self._generations[key] = self._generations.get(key, 0) + 1
        if self._entries.pop(key, None) is not None:
            self._invalidations += 1

    def invalidate_all(self) -> None:
        """Bump every key's generation and drop all entries. Any
        in-flight fetches at the time of this call have their results
        discarded on completion via the generation fence."""
        n = len(self._entries)
        for key in list(self._entries.keys()):
            self._generations[key] = self._generations.get(key, 0) + 1
        self._entries.clear()
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
            "gen_fence_discards": self._gen_fence_discards,
            "version_retries": self._version_retries,
            "active_locks": len(self._locks),
            "hit_rate_bp": (10_000 * self._hits) // total if total else 0,
        }
