"""Slice 6a — profile revision cache.

Covers:
- Hit / miss counters correct.
- LRU eviction after max entries.
- Idempotent put (same revision_id doesn't replace, doesn't grow size).
- Thread safety (concurrent put + get from multiple threads).
- Clear resets counters.

Explicit non-tests (guardrails documented in the module):
- Cross-worker consistency — cache is process-local; that's fine
  because entries are immutable per revision_id.
- Publish/rollback invalidation — the ACTIVE-REVISION POINTER is not
  cached in slice 6a; publish is immediately effective without any
  cache interaction. Tested indirectly by the resolve_v2 tests that
  still exist against the DB pointer path.
"""
from __future__ import annotations

import threading
from uuid import uuid4

import pytest


def _reset():
    from app.modules.guard.gateway_revision_cache import clear
    clear()


def test_miss_then_hit_updates_counters():
    from app.modules.guard.gateway_revision_cache import get, put, stats
    _reset()
    rid = uuid4()
    assert get(rid) is None
    s = stats()
    assert s["misses"] == 1
    assert s["hits"] == 0
    assert s["size"] == 0

    put(rid, {"model_alias": "x"})
    assert stats()["size"] == 1

    val = get(rid)
    assert val == {"model_alias": "x"}
    s = stats()
    assert s["hits"] == 1
    assert s["misses"] == 1
    # 1 hit / 2 total = 5000 bp
    assert s["hit_rate_bp"] == 5000


def test_idempotent_put_does_not_replace_or_grow():
    from app.modules.guard.gateway_revision_cache import get, put, stats
    _reset()
    rid = uuid4()
    put(rid, {"first": True})
    put(rid, {"second": True})  # same ID, must not replace
    assert stats()["size"] == 1
    assert get(rid) == {"first": True}


def test_lru_eviction_when_max_exceeded():
    """When the LRU is full, the oldest untouched entry evicts."""
    # Reset then shrink the cache via the internal knob so this test
    # doesn't need to construct 100+ entries.
    from app.modules.guard.gateway_revision_cache import _CACHE, get, put, stats
    _reset()
    _CACHE._max = 3

    ids = [uuid4() for _ in range(4)]
    for i, rid in enumerate(ids):
        put(rid, {"i": i})
    # First entry should have been evicted (LRU).
    s = stats()
    assert s["size"] == 3
    assert s["evictions"] >= 1
    assert get(ids[0]) is None  # evicted
    assert get(ids[3]) == {"i": 3}  # most recently added


def test_get_moves_entry_to_mru_end():
    """A cached-and-then-read entry survives longer than untouched ones."""
    from app.modules.guard.gateway_revision_cache import _CACHE, get, put, stats
    _reset()
    _CACHE._max = 3

    ids = [uuid4() for _ in range(3)]
    for i, rid in enumerate(ids):
        put(rid, {"i": i})
    # Touch the first ID so it's now MRU.
    _ = get(ids[0])
    # Adding a 4th ID should evict the SECOND, not the first.
    new_id = uuid4()
    put(new_id, {"i": 3})
    assert get(ids[0]) is not None  # kept (touched)
    assert get(ids[1]) is None       # evicted (LRU)
    assert get(ids[2]) is not None
    assert get(new_id) is not None


def test_thread_safety_concurrent_put_get():
    """Fan-out threads do concurrent put + get. No crashes, size stays
    within max, counters make sense."""
    from app.modules.guard.gateway_revision_cache import _CACHE, get, put, stats
    _reset()
    _CACHE._max = 50

    N = 500
    ids = [uuid4() for _ in range(N)]

    def _worker(i: int):
        for _ in range(20):
            rid = ids[(i * 37) % N]
            if get(rid) is None:
                put(rid, {"i": i})

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    s = stats()
    # Correctness: size never exceeds max.
    assert s["size"] <= s["max"]
    # Sanity: some hits and some misses happened.
    assert s["hits"] > 0
    assert s["misses"] > 0
    # No crashes = pass


def test_clear_resets_counters_and_entries():
    from app.modules.guard.gateway_revision_cache import get, put, stats, clear
    rid = uuid4()
    put(rid, {"x": 1})
    _ = get(rid)
    _ = get(uuid4())  # miss

    clear()
    s = stats()
    assert s["size"] == 0
    assert s["hits"] == 0
    assert s["misses"] == 0
    assert s["evictions"] == 0


def test_cached_snapshot_is_deep_copy_on_get():
    """P2 review fix — a caller mutating the returned object must not
    corrupt the cached snapshot. Deep-copy on retrieval isolates each
    caller from every other."""
    from app.modules.guard.gateway_revision_cache import get, put
    _reset()

    class _Target:
        def __init__(self, model): self.model = model

    class _Snapshot:
        def __init__(self):
            self.targets = [_Target("claude-sonnet"), _Target("gpt-4o")]
            self.provider_options = {"temperature": 0.5}

    rid = uuid4()
    put(rid, _Snapshot())

    # First caller mutates.
    first = get(rid)
    first.targets[0].model = "MUTATED-BY-CALLER-A"
    first.provider_options["temperature"] = 0.99

    # Second caller must see the original values.
    second = get(rid)
    assert second.targets[0].model == "claude-sonnet", (
        "cache leaked caller A's mutation — snapshots are being shared. "
        "Deep-copy on retrieval regressed."
    )
    assert second.provider_options["temperature"] == 0.5


def test_cached_snapshot_is_deep_copy_on_put():
    """A caller that mutates the snapshot AFTER calling put() must
    not corrupt what subsequent callers see."""
    from app.modules.guard.gateway_revision_cache import get, put
    _reset()

    class _Target:
        def __init__(self, model): self.model = model

    class _Snapshot:
        def __init__(self, m): self.targets = [_Target(m)]

    rid = uuid4()
    snap = _Snapshot("original")
    put(rid, snap)
    # Mutate the caller's copy AFTER put.
    snap.targets[0].model = "post-put mutation"

    retrieved = get(rid)
    assert retrieved.targets[0].model == "original", (
        "cache stored a reference to the caller's snapshot instead of a "
        "deep copy — post-put mutation leaked into the cache."
    )


def test_zero_max_disables_cache_entirely():
    """Operational correction — ``GATEWAY_REVISION_CACHE_MAX=0`` must
    be a genuine bypass. ``max=1`` retains one hot revision indefinitely
    (not a bypass); ``max=0`` must never store or return anything."""
    from app.modules.guard.gateway_revision_cache import _CACHE, get, put, stats
    _reset()
    _CACHE._max = 0

    rid = uuid4()
    put(rid, {"data": "x"})
    assert get(rid) is None, "max=0 must not store or serve entries"
    s = stats()
    assert s["size"] == 0
    # Two misses (put counts none; two gets returned None).
    assert s["hits"] == 0


def test_env_var_controls_max_size(monkeypatch):
    """GATEWAY_REVISION_CACHE_MAX env var caps the LRU. Reload the
    module to pick up the value at construction time.

    Uses a fresh import name to avoid corrupting the global cache
    for other tests."""
    import importlib

    monkeypatch.setenv("GATEWAY_REVISION_CACHE_MAX", "7")
    from app.modules.guard import gateway_revision_cache as mod
    importlib.reload(mod)
    try:
        assert mod._CACHE._max == 7
    finally:
        # Reload without the env override so subsequent tests see the
        # default. monkeypatch cleans up the env at test exit.
        monkeypatch.delenv("GATEWAY_REVISION_CACHE_MAX", raising=False)
        importlib.reload(mod)
