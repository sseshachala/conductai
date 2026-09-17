"""Slice 6e — versioned-cache primitive tests.

Covers:
- Cache hit / miss.
- Bounded refresh — entry serves after TTL still triggers refetch.
- Version fencing — min_version rejects an entry too old.
- Single-flight refresh — concurrent callers only trigger one fetch.
- Invalidation — invalidate() drops the entry.
- Missed-event recovery — if invalidation is missed, the bounded
  refresh path eventually picks up the truth.
- LRU-ish max eviction.
"""
from __future__ import annotations

import asyncio
import time

import pytest


@pytest.mark.asyncio
async def test_first_get_fetches_second_get_hits():
    from app.core.versioned_cache import VersionedCache

    calls = 0

    async def _fetch(key: str):
        nonlocal calls
        calls += 1
        return f"value-{key}", 1

    cache = VersionedCache(fetch=_fetch, refresh_interval_seconds=60)
    assert await cache.get("a") == "value-a"
    assert await cache.get("a") == "value-a"
    assert calls == 1  # second get was a hit


@pytest.mark.asyncio
async def test_stale_entry_triggers_refetch():
    from app.core.versioned_cache import VersionedCache

    calls = 0
    ret_version = 1

    async def _fetch(key: str):
        nonlocal calls
        calls += 1
        return f"v{calls}", ret_version

    # Very short refresh interval so time.monotonic passes it immediately.
    cache = VersionedCache(fetch=_fetch, refresh_interval_seconds=0.001)
    await cache.get("a")
    await asyncio.sleep(0.01)
    await cache.get("a")
    assert calls == 2, "stale entry must trigger refetch"


@pytest.mark.asyncio
async def test_min_version_rejects_older_cached_entry():
    from app.core.versioned_cache import VersionedCache

    calls = 0
    latest = 5

    async def _fetch(key: str):
        nonlocal calls
        calls += 1
        return f"v{calls}", latest

    cache = VersionedCache(fetch=_fetch, refresh_interval_seconds=60)
    # First get — populates with version=5.
    await cache.get("a")
    # Now source truth is at version 10 — cached entry version 5 must
    # be rejected on read with min_version=10.
    latest = 10
    await cache.get("a", min_version=10)
    assert calls == 2, "min_version=10 must reject the version-5 entry"


@pytest.mark.asyncio
async def test_single_flight_only_one_fetch_per_key_race():
    """N concurrent callers on a cold key: only ONE fetch runs."""
    from app.core.versioned_cache import VersionedCache

    calls = 0
    barrier = asyncio.Event()

    async def _fetch(key: str):
        nonlocal calls
        calls += 1
        await barrier.wait()  # block until test releases
        return "value", 1

    cache = VersionedCache(fetch=_fetch, refresh_interval_seconds=60)

    async def _get():
        return await cache.get("a")

    tasks = [asyncio.create_task(_get()) for _ in range(10)]
    # Let all tasks reach the lock + one enter fetch.
    await asyncio.sleep(0.05)
    assert calls == 1, "single-flight broken — multiple fetches raced"
    barrier.set()
    results = await asyncio.gather(*tasks)
    assert all(r == "value" for r in results)


@pytest.mark.asyncio
async def test_invalidate_drops_entry():
    from app.core.versioned_cache import VersionedCache

    calls = 0

    async def _fetch(key: str):
        nonlocal calls
        calls += 1
        return f"v{calls}", 1

    cache = VersionedCache(fetch=_fetch, refresh_interval_seconds=60)
    await cache.get("a")
    cache.invalidate("a")
    await cache.get("a")
    assert calls == 2, "invalidate should force refetch on next get"


@pytest.mark.asyncio
async def test_invalidate_all_drops_everything():
    from app.core.versioned_cache import VersionedCache

    async def _fetch(key: str):
        return f"v-{key}", 1

    cache = VersionedCache(fetch=_fetch, refresh_interval_seconds=60)
    for k in ("a", "b", "c"):
        await cache.get(k)
    assert cache.stats()["size"] == 3
    cache.invalidate_all()
    assert cache.stats()["size"] == 0


@pytest.mark.asyncio
async def test_missed_invalidation_eventually_recovers_via_refresh():
    """The reviewer's core correctness scenario: even if the
    invalidation bus drops a message, the bounded-refresh path
    picks up the truth on next expiry."""
    from app.core.versioned_cache import VersionedCache

    truth = {"data": "old", "version": 1}

    async def _fetch(key: str):
        return truth["data"], truth["version"]

    # Refresh interval is 50ms — the bounded window for stale service.
    cache = VersionedCache(fetch=_fetch, refresh_interval_seconds=0.05)
    v = await cache.get("a")
    assert v == "old"

    # Truth flips. Invalidation event is "lost" — no invalidate() call.
    truth["data"] = "new"
    truth["version"] = 2

    # Within the refresh interval, cached "old" is still served.
    v = await cache.get("a")
    assert v == "old"

    # Wait past the refresh interval — bounded-refresh path kicks in.
    await asyncio.sleep(0.1)
    v = await cache.get("a")
    assert v == "new", "bounded refresh should have caught up despite missed event"


@pytest.mark.asyncio
async def test_max_entries_evicts_oldest_fetched():
    from app.core.versioned_cache import VersionedCache

    async def _fetch(key: str):
        return f"v-{key}", 1

    cache = VersionedCache(fetch=_fetch, refresh_interval_seconds=60, max_entries=3)
    await cache.get("a")
    await asyncio.sleep(0.01)
    await cache.get("b")
    await asyncio.sleep(0.01)
    await cache.get("c")
    await asyncio.sleep(0.01)
    # 4th add evicts oldest (a).
    await cache.get("d")
    assert cache.stats()["size"] == 3


@pytest.mark.asyncio
async def test_stats_shape():
    from app.core.versioned_cache import VersionedCache

    async def _fetch(key: str):
        return "v", 1

    cache = VersionedCache(fetch=_fetch, refresh_interval_seconds=1.0)
    await cache.get("a")
    await cache.get("a")
    cache.invalidate("a")
    s = cache.stats()
    assert s["size"] == 0
    assert s["hits"] == 1
    assert s["misses"] == 1
    assert s["invalidations"] == 1
    assert s["refresh_interval_seconds"] == 1.0
    assert s["hit_rate_bp"] == 5000


def test_refresh_interval_must_be_positive():
    from app.core.versioned_cache import VersionedCache
    with pytest.raises(ValueError):
        VersionedCache(fetch=lambda k: None, refresh_interval_seconds=0)
