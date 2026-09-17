"""PR 6c — effective-policy cache correctness proofs.

Reviewer directive from earlier PRs: prove revocation, expiry, and
missed-event behaviour before shipping. These tests wire the same
in-memory bus stub used by PR 6b (auth cache) canary so the whole
chain — publisher, bus, subscriber, cache state — is exercised without
Redis.
"""
from __future__ import annotations

import asyncio
import copy
import time

import pytest


# ── In-memory bus stub ──────────────────────────────────────────────

class _InMemoryBus:
    def __init__(self):
        self._handlers: dict[str, list] = {}

    def subscribe(self, kinds, handler):
        for k in kinds:
            self._handlers.setdefault(k, []).append(handler)

    async def publish(self, kind: str, key: str, version: int = 0):
        for handler in self._handlers.get(kind, []):
            await handler({"kind": kind, "key": key, "version": version})


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_singleton():
    from app.core.effective_policy_cache import reset_effective_policy_cache_for_tests
    reset_effective_policy_cache_for_tests()
    yield
    reset_effective_policy_cache_for_tests()


def _rules(action="allow"):
    return [{"id": "rule-1", "action": action, "match": {"tool": "*"}}]


# ── Kill switch ─────────────────────────────────────────────────────

def test_kill_switch_off_by_default(monkeypatch):
    """Without EFFECTIVE_POLICY_CACHE_ENABLED, get/put are no-ops."""
    monkeypatch.delenv("EFFECTIVE_POLICY_CACHE_ENABLED", raising=False)
    from app.core.effective_policy_cache import EffectivePolicyCache
    c = EffectivePolicyCache()
    fence = c.capture_fence("ws-1")
    assert c.put_if_fresh("ws-1", "agent", _rules(), fence) is False
    assert c.get("ws-1", "agent") is None


# ── Cold miss / warm hit ────────────────────────────────────────────

def test_cold_miss_then_warm_hit(monkeypatch):
    monkeypatch.setenv("EFFECTIVE_POLICY_CACHE_ENABLED", "true")
    from app.core.effective_policy_cache import EffectivePolicyCache
    c = EffectivePolicyCache(ttl_seconds=30.0)

    assert c.get("ws-1", "agent") is None
    assert c.stats()["misses"] == 1

    fence = c.capture_fence("ws-1")
    assert c.put_if_fresh("ws-1", "agent", _rules(), fence) is True
    assert c.stats()["size"] == 1

    hit = c.get("ws-1", "agent")
    assert hit == _rules()
    assert c.stats()["hits"] == 1


# ── Deep-copy semantics ─────────────────────────────────────────────

def test_get_returns_deep_copy_caller_mutation_does_not_leak(monkeypatch):
    monkeypatch.setenv("EFFECTIVE_POLICY_CACHE_ENABLED", "true")
    from app.core.effective_policy_cache import EffectivePolicyCache
    c = EffectivePolicyCache()

    original = _rules()
    fence = c.capture_fence("ws-1")
    c.put_if_fresh("ws-1", "agent", original, fence)

    first = c.get("ws-1", "agent")
    first[0]["action"] = "block"  # caller-side mutation

    second = c.get("ws-1", "agent")
    assert second[0]["action"] == "allow", (
        "caller mutation of a returned rule list leaked into the cache "
        "— deep-copy on read is broken"
    )


def test_put_snapshots_caller_owned_list(monkeypatch):
    """Mutating the source list after put must not affect the cached
    entry — otherwise a naive rebuild that re-uses a scratch list can
    poison every subsequent read."""
    monkeypatch.setenv("EFFECTIVE_POLICY_CACHE_ENABLED", "true")
    from app.core.effective_policy_cache import EffectivePolicyCache
    c = EffectivePolicyCache()

    source = _rules()
    fence = c.capture_fence("ws-1")
    c.put_if_fresh("ws-1", "agent", source, fence)

    source[0]["action"] = "block"  # writer mutates after put

    assert c.get("ws-1", "agent")[0]["action"] == "allow"


# ── TTL bounded refresh (the correctness ceiling) ───────────────────

def test_ttl_expires_entries(monkeypatch):
    monkeypatch.setenv("EFFECTIVE_POLICY_CACHE_ENABLED", "true")
    from app.core.effective_policy_cache import EffectivePolicyCache
    c = EffectivePolicyCache(ttl_seconds=0.05)

    fence = c.capture_fence("ws-1")
    c.put_if_fresh("ws-1", "agent", _rules(), fence)
    assert c.get("ws-1", "agent") is not None

    time.sleep(0.1)
    assert c.get("ws-1", "agent") is None, "TTL did not expire the entry"


def test_missed_invalidation_recovers_via_ttl(monkeypatch):
    """The reviewer's critical scenario. Cache is populated. The bus
    event never arrives. TTL is the correctness ceiling — after TTL,
    the next call re-fetches and sees the truth."""
    monkeypatch.setenv("EFFECTIVE_POLICY_CACHE_ENABLED", "true")
    from app.core.effective_policy_cache import EffectivePolicyCache
    c = EffectivePolicyCache(ttl_seconds=0.05)

    fence = c.capture_fence("ws-1")
    c.put_if_fresh("ws-1", "agent", _rules("allow"), fence)
    assert c.get("ws-1", "agent")[0]["action"] == "allow"

    # Server-side state changes; no bus event fires.
    time.sleep(0.1)
    # Post-TTL the cache reports miss so the caller falls through to DB.
    assert c.get("ws-1", "agent") is None


# ── Invalidation ────────────────────────────────────────────────────

def test_invalidate_workspace_scoped_to_workspace(monkeypatch):
    monkeypatch.setenv("EFFECTIVE_POLICY_CACHE_ENABLED", "true")
    from app.core.effective_policy_cache import EffectivePolicyCache
    c = EffectivePolicyCache()

    f1 = c.capture_fence("ws-1")
    f2 = c.capture_fence("ws-2")
    c.put_if_fresh("ws-1", "agent", _rules(), f1)
    c.put_if_fresh("ws-2", "agent", _rules(), f2)
    assert c.stats()["size"] == 2

    c.invalidate_workspace("ws-1")
    assert c.get("ws-1", "agent") is None
    assert c.get("ws-2", "agent") is not None
    assert c.stats()["invalidations_workspace"] == 1


def test_invalidate_all_drops_every_entry(monkeypatch):
    monkeypatch.setenv("EFFECTIVE_POLICY_CACHE_ENABLED", "true")
    from app.core.effective_policy_cache import EffectivePolicyCache
    c = EffectivePolicyCache()

    for i in range(5):
        f = c.capture_fence(f"ws-{i}")
        c.put_if_fresh(f"ws-{i}", "agent", _rules(), f)
    assert c.stats()["size"] == 5

    c.invalidate_all()
    assert c.stats()["size"] == 0
    for i in range(5):
        assert c.get(f"ws-{i}", "agent") is None


# ── Generation fence (the in-flight race) ───────────────────────────

def test_invalidation_during_fetch_discards_result(monkeypatch):
    """Reviewer's other critical scenario. An invalidation races ahead
    of a build in progress; the build must not overwrite the cache
    with the value it fetched before the invalidation fired."""
    monkeypatch.setenv("EFFECTIVE_POLICY_CACHE_ENABLED", "true")
    from app.core.effective_policy_cache import EffectivePolicyCache
    c = EffectivePolicyCache()

    fence = c.capture_fence("ws-1")
    # Simulated: invalidation fires between capture_fence and put_if_fresh.
    c.invalidate_workspace("ws-1")
    stored = c.put_if_fresh("ws-1", "agent", _rules(), fence)

    assert stored is False, "in-flight result was stored despite invalidation"
    assert c.get("ws-1", "agent") is None
    assert c.stats()["fence_discards"] == 1


def test_global_invalidation_fences_workspace_scoped_fetch(monkeypatch):
    """Global gen bump must also veto a workspace-scoped fetch — a
    pack update affects every workspace."""
    monkeypatch.setenv("EFFECTIVE_POLICY_CACHE_ENABLED", "true")
    from app.core.effective_policy_cache import EffectivePolicyCache
    c = EffectivePolicyCache()

    fence = c.capture_fence("ws-1")
    c.invalidate_all()  # global gen bump — mimics pack update
    stored = c.put_if_fresh("ws-1", "agent", _rules(), fence)

    assert stored is False
    assert c.stats()["fence_discards"] == 1


# ── Bus wiring E2E ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bus_event_drops_workspace_entries(monkeypatch):
    monkeypatch.setenv("EFFECTIVE_POLICY_CACHE_ENABLED", "true")
    from app.core.effective_policy_cache import EffectivePolicyCache
    c = EffectivePolicyCache()
    bus = _InMemoryBus()
    c.attach_bus(bus)

    f1 = c.capture_fence("ws-1")
    f2 = c.capture_fence("ws-2")
    c.put_if_fresh("ws-1", "agent", _rules(), f1)
    c.put_if_fresh("ws-2", "agent", _rules(), f2)

    await bus.publish("guard.policy.invalidated", "ws-1")

    assert c.get("ws-1", "agent") is None
    assert c.get("ws-2", "agent") is not None
    assert c.stats()["bus_events_handled"] == 1
    assert c.stats()["invalidations_workspace"] == 1


@pytest.mark.asyncio
async def test_pack_updated_event_drops_all(monkeypatch):
    monkeypatch.setenv("EFFECTIVE_POLICY_CACHE_ENABLED", "true")
    from app.core.effective_policy_cache import EffectivePolicyCache
    c = EffectivePolicyCache()
    bus = _InMemoryBus()
    c.attach_bus(bus)

    for i in range(3):
        f = c.capture_fence(f"ws-{i}")
        c.put_if_fresh(f"ws-{i}", "agent", _rules(), f)

    await bus.publish("guard.pack.updated", "conduct-base")

    assert c.stats()["size"] == 0
    assert c.stats()["invalidations_all"] == 1


# ── Capacity eviction ───────────────────────────────────────────────

def test_capacity_evicts_earliest_expiry(monkeypatch):
    monkeypatch.setenv("EFFECTIVE_POLICY_CACHE_ENABLED", "true")
    from app.core.effective_policy_cache import EffectivePolicyCache
    c = EffectivePolicyCache(max_entries=2)

    for i in range(3):
        f = c.capture_fence(f"ws-{i}")
        c.put_if_fresh(f"ws-{i}", "agent", _rules(), f)
        time.sleep(0.01)  # ensure distinct expiry ordering

    assert c.stats()["size"] == 2
    # ws-0 (earliest expiry) was evicted.
    assert c.get("ws-0", "agent") is None
    assert c.get("ws-2", "agent") is not None


def test_max_entries_zero_is_genuine_bypass(monkeypatch):
    """max_entries=0 must retain nothing — a hard bypass, not a soft
    cap of one entry (auth cache reviewer flagged this shape)."""
    monkeypatch.setenv("EFFECTIVE_POLICY_CACHE_ENABLED", "true")
    from app.core.effective_policy_cache import EffectivePolicyCache
    c = EffectivePolicyCache(max_entries=0)

    fence = c.capture_fence("ws-1")
    assert c.put_if_fresh("ws-1", "agent", _rules(), fence) is False
    assert c.get("ws-1", "agent") is None


# ── Publisher helpers ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publisher_helpers_emit_correct_events(monkeypatch):
    monkeypatch.setenv("INVALIDATION_BUS_ENABLED", "true")
    from app.core import policy_events
    from app.core import invalidation_bus as bus_mod

    calls: list[tuple[str, str]] = []

    class _RecordingBus:
        async def publish(self, kind, key, version):
            calls.append((kind, key))

    monkeypatch.setattr(bus_mod, "get_bus", lambda: _RecordingBus())

    policy_events.publish_policy_invalidated("ws-abc")
    policy_events.publish_pack_updated("conduct-base")

    await asyncio.sleep(0.01)

    assert ("guard.policy.invalidated", "ws-abc") in calls
    assert ("guard.pack.updated", "conduct-base") in calls
