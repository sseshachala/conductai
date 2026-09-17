"""Slice 6b — auth cache tests.

Every reviewer concern gets an explicit test:
- Fingerprint keying (raw token never stored).
- TTL = min(cache_ttl, token_ttl).
- Cache disabled by kill switch.
- All five invalidation triggers (token / identity disable / risk-tier /
  permission / workspace).
- Bus integration wires all five.
- Single-flight resolve on cold cache.
- Negative results not cached (would trap clients).
- Lock table stays bounded.
- Multi-key invalidation via secondary indices.
"""
from __future__ import annotations

import asyncio
import hashlib
import time

import pytest


def _make_auth(**overrides):
    """Test helper — build a CachedAuth with sensible defaults."""
    from app.core.auth_cache import CachedAuth
    defaults = dict(
        workspace_id="ws-1",
        clerk_user_id="user-1",
        agent_identity_id="ident-1",
        agent_risk_tier="tier_2",
        is_internal=False,
        token_expires_at=None,
    )
    defaults.update(overrides)
    return CachedAuth(**defaults)


# ── Kill switch ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_disabled_kill_switch_bypasses_cache(monkeypatch):
    monkeypatch.delenv("AUTH_CACHE_ENABLED", raising=False)
    from app.core.auth_cache import AuthCache

    calls = 0

    async def _fetch(token):
        nonlocal calls
        calls += 1
        return _make_auth()

    cache = AuthCache(fetch=_fetch)
    await cache.resolve("t-1")
    await cache.resolve("t-1")
    assert calls == 2, "kill switch OFF — every resolve must call fetch"


# ── Fingerprint keying ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_raw_token_never_stored(monkeypatch):
    """Cache keys are SHA-256 hashes, not raw tokens."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache, _fingerprint

    async def _fetch(token):
        return _make_auth()

    cache = AuthCache(fetch=_fetch)
    token = "guard-mt-super-secret-bearer-abcdefg"
    await cache.resolve(token)

    # The raw token must NOT appear as a key.
    assert token not in cache._entries
    # The fingerprint MUST appear.
    assert _fingerprint(token) in cache._entries
    # The raw token must NOT appear anywhere as a value string either.
    for k, entry in cache._entries.items():
        assert token not in k
        assert token not in str(entry.auth)


# ── TTL semantics ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_hit_within_ttl(monkeypatch):
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache

    calls = 0

    async def _fetch(token):
        nonlocal calls
        calls += 1
        return _make_auth()

    cache = AuthCache(fetch=_fetch, cache_ttl_seconds=60.0)
    await cache.resolve("t-1")
    await cache.resolve("t-1")
    assert calls == 1


@pytest.mark.asyncio
async def test_expiry_after_cache_ttl(monkeypatch):
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache

    calls = 0

    async def _fetch(token):
        nonlocal calls
        calls += 1
        return _make_auth()

    cache = AuthCache(fetch=_fetch, cache_ttl_seconds=0.05)
    await cache.resolve("t-1")
    await asyncio.sleep(0.1)
    await cache.resolve("t-1")
    assert calls == 2, "entry must expire after cache_ttl"


@pytest.mark.asyncio
async def test_ttl_bounded_by_token_expiry(monkeypatch):
    """Effective TTL = min(cache_ttl, token_ttl). Token expires in 50ms,
    cache TTL is 60s → entry must expire in ~50ms not 60s."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache

    calls = 0
    token_exp = time.time() + 0.05  # token expires in 50ms wall-clock

    async def _fetch(token):
        nonlocal calls
        calls += 1
        return _make_auth(token_expires_at=token_exp)

    cache = AuthCache(fetch=_fetch, cache_ttl_seconds=60.0)
    await cache.resolve("t-1")
    await asyncio.sleep(0.1)  # past token expiry, within cache TTL
    await cache.resolve("t-1")
    assert calls == 2, (
        "cache TTL is 60s but token expired 50ms in — entry MUST "
        "expire on token expiry, not cache TTL"
    )


@pytest.mark.asyncio
async def test_already_expired_token_not_cached(monkeypatch):
    """A token that's already expired at fetch time is returned but
    NOT stored — no future request can use it."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache

    async def _fetch(token):
        return _make_auth(token_expires_at=time.time() - 10)  # past

    cache = AuthCache(fetch=_fetch, cache_ttl_seconds=60.0)
    await cache.resolve("t-1")
    assert cache.stats()["size"] == 0, "expired token must not be cached"


# ── Negative caching ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_negative_result_not_cached(monkeypatch):
    """A token that doesn't resolve (fetch returns None) must NOT be
    cached — the next request retries fetch."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache

    calls = 0

    async def _fetch(token):
        nonlocal calls
        calls += 1
        return None

    cache = AuthCache(fetch=_fetch, cache_ttl_seconds=60.0)
    r1 = await cache.resolve("t-unknown")
    r2 = await cache.resolve("t-unknown")
    assert r1 is None and r2 is None
    assert calls == 2, "negative result must not cache"
    assert cache.stats()["negative_hits"] == 2


# ── Single-flight ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_single_flight_concurrent_resolve(monkeypatch):
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache

    calls = 0
    let_finish = asyncio.Event()

    async def _fetch(token):
        nonlocal calls
        calls += 1
        await let_finish.wait()
        return _make_auth()

    cache = AuthCache(fetch=_fetch, cache_ttl_seconds=60.0)
    tasks = [asyncio.create_task(cache.resolve("t-1")) for _ in range(20)]
    await asyncio.sleep(0.05)
    assert calls == 1, "single-flight broken — multiple fetches raced"
    let_finish.set()
    await asyncio.gather(*tasks)


# ── Invalidation triggers ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_invalidate_token_drops_entry(monkeypatch):
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache

    async def _fetch(token):
        return _make_auth()

    cache = AuthCache(fetch=_fetch)
    await cache.resolve("t-1")
    cache.invalidate_token("t-1")
    assert cache.stats()["size"] == 0
    assert cache.stats()["invalidations_token"] == 1


@pytest.mark.asyncio
async def test_invalidate_identity_drops_all_entries_for_identity(monkeypatch):
    """One identity might have multiple tokens (session token +
    long-lived API token). Disabling the identity must drop ALL of
    them."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache

    async def _fetch(token):
        return _make_auth(agent_identity_id="ident-x")

    cache = AuthCache(fetch=_fetch)
    await cache.resolve("token-a")
    await cache.resolve("token-b")
    await cache.resolve("token-c")
    assert cache.stats()["size"] == 3

    cache.invalidate_identity("ident-x")
    assert cache.stats()["size"] == 0
    assert cache.stats()["invalidations_identity"] == 1


@pytest.mark.asyncio
async def test_invalidate_workspace_drops_all_entries_for_workspace(monkeypatch):
    """A permission change at workspace level affects every token for
    users/identities in that workspace."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache

    async def _fetch(token):
        return _make_auth(workspace_id="ws-target", agent_identity_id=token)

    cache = AuthCache(fetch=_fetch)
    await cache.resolve("t-1")
    await cache.resolve("t-2")
    await cache.resolve("t-3")
    assert cache.stats()["size"] == 3

    cache.invalidate_workspace("ws-target")
    assert cache.stats()["size"] == 0
    assert cache.stats()["invalidations_workspace"] == 1


@pytest.mark.asyncio
async def test_secondary_indices_cleaned_up_after_invalidation(monkeypatch):
    """After invalidating everything for an identity, the identity
    index entry must be gone too (no zombie index growth)."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache

    async def _fetch(token):
        return _make_auth(agent_identity_id="ident-x")

    cache = AuthCache(fetch=_fetch)
    await cache.resolve("t-1")
    await cache.resolve("t-2")
    assert cache.stats()["identity_index_size"] == 1

    cache.invalidate_identity("ident-x")
    assert cache.stats()["identity_index_size"] == 0


# ── Bus integration ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bus_events_fire_correct_invalidation(monkeypatch):
    """Wire the cache to a fake bus. Fire each of the 5 event kinds.
    Assert the correct invalidation method fires for each."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache, _fingerprint

    async def _fetch(token):
        return _make_auth(
            workspace_id="ws-x",
            agent_identity_id="ident-x",
        )

    handlers: dict[str, list] = {}

    class _FakeBus:
        def subscribe(self, kinds, handler):
            for k in kinds:
                handlers.setdefault(k, []).append(handler)

    cache = AuthCache(fetch=_fetch, invalidation_bus=_FakeBus())

    # Populate the cache first.
    await cache.resolve("token-1")
    fp = _fingerprint("token-1")
    assert cache.stats()["size"] == 1

    # Fire auth.token.revoked → should invalidate by fingerprint.
    for h in handlers["auth.token.revoked"]:
        await h({"kind": "auth.token.revoked", "key": fp})
    assert cache.stats()["size"] == 0
    assert cache.stats()["invalidations_token"] == 1

    # Repopulate, fire auth.identity.disabled → invalidate by identity.
    await cache.resolve("token-2")
    for h in handlers["auth.identity.disabled"]:
        await h({"kind": "auth.identity.disabled", "key": "ident-x"})
    assert cache.stats()["size"] == 0
    assert cache.stats()["invalidations_identity"] == 1

    # Repopulate, fire auth.risk_tier.changed → invalidate by identity.
    await cache.resolve("token-3")
    for h in handlers["auth.risk_tier.changed"]:
        await h({"kind": "auth.risk_tier.changed", "key": "ident-x"})
    assert cache.stats()["size"] == 0
    assert cache.stats()["invalidations_identity"] == 2

    # Repopulate, fire auth.permission.changed → invalidate by workspace.
    await cache.resolve("token-4")
    for h in handlers["auth.permission.changed"]:
        await h({"kind": "auth.permission.changed", "key": "ws-x"})
    assert cache.stats()["size"] == 0
    assert cache.stats()["invalidations_workspace"] == 1

    # Repopulate, fire auth.workspace.changed → invalidate by workspace.
    await cache.resolve("token-5")
    for h in handlers["auth.workspace.changed"]:
        await h({"kind": "auth.workspace.changed", "key": "ws-x"})
    assert cache.stats()["size"] == 0
    assert cache.stats()["invalidations_workspace"] == 2

    assert cache.stats()["bus_events_handled"] == 5


# ── Lock lifecycle ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_lock_table_bounded_after_many_resolves(monkeypatch):
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache

    async def _fetch(token):
        return _make_auth(agent_identity_id=token)

    cache = AuthCache(fetch=_fetch)
    for i in range(101):
        await cache.resolve(f"t-{i}")

    stats = cache.stats()
    assert stats["active_locks"] <= 1, (
        f"lock table grew unboundedly: {stats['active_locks']}"
    )


# ── Bounded size ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_max_entries_evicts_oldest_expiring(monkeypatch):
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache

    async def _fetch(token):
        return _make_auth(agent_identity_id=token)

    cache = AuthCache(fetch=_fetch, max_entries=3)
    for i in range(5):
        await cache.resolve(f"t-{i}")
        await asyncio.sleep(0.001)  # deterministic expires_at ordering

    stats = cache.stats()
    assert stats["size"] == 3
    assert stats["evictions"] == 2


# ── Stats ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stats_reports_all_counters(monkeypatch):
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import AuthCache

    async def _fetch(token):
        return _make_auth()

    cache = AuthCache(fetch=_fetch)
    stats = cache.stats()
    expected = {
        "enabled", "size", "max", "ttl_seconds", "hits", "misses",
        "negative_hits", "invalidations_token", "invalidations_identity",
        "invalidations_workspace", "evictions", "bus_events_handled",
        "active_locks", "identity_index_size", "workspace_index_size",
        "hit_rate_bp",
    }
    assert set(stats.keys()) == expected
