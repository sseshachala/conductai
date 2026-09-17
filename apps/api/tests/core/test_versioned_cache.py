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
async def test_fetched_value_below_min_version_raises_after_deadline():
    """P1 review fix — a fetch that returns version < min_version must
    NOT be returned to a caller that asked for the higher version.
    Retry within bounded deadline; on expiry, raise VersionUnavailable.
    """
    from app.core.versioned_cache import VersionedCache, VersionUnavailable

    async def _fetch(key: str):
        return "old", 1  # never advances

    cache = VersionedCache(
        fetch=_fetch,
        refresh_interval_seconds=60,
        retry_backoff_seconds=0.01,
    )
    with pytest.raises(VersionUnavailable) as excinfo:
        await cache.get("a", min_version=42, deadline_seconds=0.05)
    assert excinfo.value.min_version == 42
    assert excinfo.value.last_version == 1
    assert excinfo.value.elapsed >= 0.05


@pytest.mark.asyncio
async def test_fetched_value_at_min_version_returns_immediately():
    """Complement to the above — when the fetch catches up to the
    requested min_version, the value is returned without further
    retry."""
    from app.core.versioned_cache import VersionedCache

    call = 0

    async def _fetch(key: str):
        nonlocal call
        call += 1
        # First call returns version 5, next call returns version 42.
        return "v", 5 if call == 1 else 42

    cache = VersionedCache(
        fetch=_fetch,
        refresh_interval_seconds=60,
        retry_backoff_seconds=0.01,
    )
    v = await cache.get("a", min_version=42, deadline_seconds=1.0)
    assert v == "v"
    assert call >= 2  # first fetch too old, second met the bar


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
async def test_generation_fence_discards_racing_fetch():
    """P1 review fix — an invalidate() that fires WHILE a fetch is in
    progress must cause the fetch's result to be DISCARDED, not
    stored + returned to subsequent readers.

    Scenario: fetch starts → invalidate fires (fence bumps) → fetch
    completes with stale value → cache must NOT store it → next get
    triggers a fresh fetch.
    """
    from app.core.versioned_cache import VersionedCache

    fetch_started = asyncio.Event()
    let_fetch_finish = asyncio.Event()
    fetch_count = 0
    result = ("old-value", 1)

    async def _fetch(key: str):
        nonlocal fetch_count
        fetch_count += 1
        fetch_started.set()
        await let_fetch_finish.wait()
        return result

    cache = VersionedCache(fetch=_fetch, refresh_interval_seconds=60)

    async def _first_get():
        return await cache.get("a")

    # Kick off first get, which begins the fetch.
    first_task = asyncio.create_task(_first_get())
    await fetch_started.wait()
    # Invalidate while fetch is in flight — bumps generation.
    cache.invalidate("a")
    # Advance the "truth" so a fresh fetch produces a different value.
    result = ("new-value", 2)
    # Let the racing fetch complete. It should discard.
    let_fetch_finish.set()
    first_result = await first_task
    # The first caller may see the old value (they were already
    # committed) OR the new one (if they retry); reviewer's actual
    # requirement is that SUBSEQUENT reads don't serve the stale
    # value.

    # Reset for the second call — fresh event so we can control it.
    fetch_started.clear()
    let_fetch_finish.clear()

    async def _second_get():
        return await cache.get("a")

    second_task = asyncio.create_task(_second_get())
    await fetch_started.wait()  # a fresh fetch DID start (proof of discard)
    let_fetch_finish.set()
    second_result = await second_task
    assert second_result == "new-value", (
        "cache served the stale fetched value even though invalidation "
        "fired mid-fetch — generation fence regressed"
    )
    assert cache.stats()["gen_fence_discards"] >= 1


@pytest.mark.asyncio
async def test_slow_fetch_does_not_extend_freshness_window():
    """P1 review fix — ``fetched_at`` is measured from fetch START, not
    completion. A 200ms fetch under a 100ms refresh interval must not
    extend the freshness window past 100ms from START.
    """
    from app.core.versioned_cache import VersionedCache

    async def _fetch(key: str):
        await asyncio.sleep(0.2)  # slow fetch (200ms)
        return "value", 1

    cache = VersionedCache(fetch=_fetch, refresh_interval_seconds=0.1)
    # First get: fetch takes 200ms; by the time it returns, the entry
    # is already older than 100ms.
    await cache.get("a")
    # Immediately retrying should trigger a refetch because the
    # freshness clock started before the first fetch completed.
    calls_before = cache.stats()["misses"]
    await cache.get("a")
    calls_after = cache.stats()["misses"]
    assert calls_after > calls_before, (
        "freshness window was measured from fetch completion instead "
        "of fetch start — slow fetch extended stale service"
    )


@pytest.mark.asyncio
async def test_lock_table_cleaned_up_across_many_keys():
    """P2 review fix — per-key locks must be reference-counted and
    removed when the last holder/waiter releases. Otherwise a
    workload with high key cardinality leaks locks.
    """
    from app.core.versioned_cache import VersionedCache

    async def _fetch(key: str):
        return f"v-{key}", 1

    # Small cache — entry-table cap doesn't bound the lock table.
    cache = VersionedCache(
        fetch=_fetch,
        refresh_interval_seconds=60,
        max_entries=2,
    )

    for i in range(101):
        await cache.get(f"key-{i}")

    stats = cache.stats()
    # Every completed get should have released its lock. Lock table
    # should be empty (or 1, if a completion is still in flight).
    assert stats["active_locks"] <= 1, (
        f"lock table grew unboundedly — {stats['active_locks']} locks "
        "retained after 101 sequential completed gets"
    )
    # Entry table is still bounded by max_entries.
    assert stats["size"] <= stats["max"]


@pytest.mark.asyncio
async def test_lock_table_bounded_after_invalidations():
    """Invalidations must not leave zombie locks behind."""
    from app.core.versioned_cache import VersionedCache

    async def _fetch(key: str):
        return "v", 1

    cache = VersionedCache(fetch=_fetch, refresh_interval_seconds=60)
    for i in range(50):
        await cache.get(f"key-{i}")
        cache.invalidate(f"key-{i}")

    # After each pair (get + invalidate), the lock should be gone.
    assert cache.stats()["active_locks"] <= 1


@pytest.mark.asyncio
async def test_single_flight_still_works_with_lock_cleanup():
    """Regression guard: the ref-count cleanup must not break
    single-flight (multiple concurrent callers on cold key = 1 fetch).
    """
    from app.core.versioned_cache import VersionedCache

    calls = 0
    let_finish = asyncio.Event()

    async def _fetch(key: str):
        nonlocal calls
        calls += 1
        await let_finish.wait()
        return "v", 1

    cache = VersionedCache(fetch=_fetch, refresh_interval_seconds=60)
    tasks = [asyncio.create_task(cache.get("a")) for _ in range(20)]
    await asyncio.sleep(0.05)
    assert calls == 1, "single-flight broken under refcount lock cleanup"
    let_finish.set()
    await asyncio.gather(*tasks)


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
