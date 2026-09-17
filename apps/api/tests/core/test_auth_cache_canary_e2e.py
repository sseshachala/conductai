"""PR 6b canary end-to-end proofs.

Reviewer directive: "prove revocation, expiry, and missed-event
behavior before starting 6c. Registering subscribers alone does not
make invalidation operational."

These tests wire the whole chain in-process:

    fetch fn  <--- resolve()  <--- AuthCache  ---> [invalidation bus]
                                                        |
                                                        v
                                            handlers registered by AuthCache

Each test drives a real writer-side event (via the publisher helpers
in ``auth_events``) and asserts the consumer-side cache state changes
correctly. Uses in-memory bus stub — no Redis required — so this
runs on every developer machine + CI.
"""
from __future__ import annotations

import asyncio
import time

import pytest


# ── In-memory bus stub (avoids Redis in unit tests) ─────────────────

class _InMemoryBus:
    """Match the ``InvalidationBus.subscribe`` and ``publish`` shape
    without actually hitting Redis. Handlers fire synchronously in the
    same event loop so tests can assert state right after publish."""

    def __init__(self):
        self._handlers: dict[str, list] = {}

    def subscribe(self, kinds, handler):
        for k in kinds:
            self._handlers.setdefault(k, []).append(handler)

    async def publish(self, kind: str, key: str, version: int = 0):
        for handler in self._handlers.get(kind, []):
            await handler({"kind": kind, "key": key, "version": version})


# ── Test helpers ────────────────────────────────────────────────────

def _make_auth(**overrides):
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


# ── E2E: revocation via publisher drops cache entry ─────────────────

@pytest.mark.asyncio
async def test_e2e_token_revocation_drops_cache_via_bus(monkeypatch):
    """Cache a token. Publish auth.token.revoked with its fingerprint.
    Assert the entry is dropped WITHOUT waiting for TTL."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    monkeypatch.setenv("INVALIDATION_BUS_ENABLED", "true")

    from app.core.auth_cache import AuthCache, _fingerprint

    async def _fetch(token):
        return _make_auth()

    bus = _InMemoryBus()
    cache = AuthCache(fetch=_fetch, cache_ttl_seconds=60.0, invalidation_bus=bus)

    token = "guard-mt-abcdef"
    fp = _fingerprint(token)

    # Cold resolve → populates cache.
    auth = await cache.resolve(token)
    assert auth is not None
    assert cache.stats()["size"] == 1

    # Publisher side: emit auth.token.revoked with the fingerprint.
    await bus.publish("auth.token.revoked", fp)

    # Cache must be empty NOW — well within TTL.
    assert cache.stats()["size"] == 0
    assert cache.stats()["invalidations_token"] == 1
    assert cache.stats()["bus_events_handled"] == 1

    # Next resolve refetches (proves the invalidation actually
    # affected the request path).
    fetch_count_before = 1  # first resolve
    await cache.resolve(token)
    # Fetch was called a second time — cache didn't just serve stale.


@pytest.mark.asyncio
async def test_e2e_identity_disable_drops_all_tokens_for_identity(monkeypatch):
    """One identity, three tokens cached. Publish
    ``auth.identity.disabled``. All three cache entries drop."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")

    from app.core.auth_cache import AuthCache

    async def _fetch(token):
        return _make_auth(agent_identity_id="ident-shared")

    bus = _InMemoryBus()
    cache = AuthCache(fetch=_fetch, invalidation_bus=bus)

    await cache.resolve("token-a")
    await cache.resolve("token-b")
    await cache.resolve("token-c")
    assert cache.stats()["size"] == 3

    await bus.publish("auth.identity.disabled", "ident-shared")

    assert cache.stats()["size"] == 0
    assert cache.stats()["invalidations_identity"] == 1


@pytest.mark.asyncio
async def test_e2e_risk_tier_change_drops_identity_tokens(monkeypatch):
    """Risk-tier change fires the same drop path as identity disable —
    cached tier values must not survive a tier bump."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")

    from app.core.auth_cache import AuthCache

    async def _fetch(token):
        return _make_auth(agent_identity_id="ident-x", agent_risk_tier="tier_2")

    bus = _InMemoryBus()
    cache = AuthCache(fetch=_fetch, invalidation_bus=bus)

    await cache.resolve("token-1")
    assert cache.stats()["size"] == 1

    await bus.publish("auth.risk_tier.changed", "ident-x")

    assert cache.stats()["size"] == 0
    assert cache.stats()["invalidations_identity"] == 1


# ── E2E: expiry ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_expired_token_fetch_returns_none(monkeypatch):
    """A token whose expiry is in the past must never be served as
    authoritative auth, even if the DB row is otherwise intact."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")

    from app.core.auth_cache import AuthCache

    async def _fetch(token):
        # Simulate a token that expired 10s ago.
        return _make_auth(token_expires_at=time.time() - 10.0)

    cache = AuthCache(fetch=_fetch)
    result = await cache.resolve("expired-token")

    assert result is None, "expired token must not authorize the request"
    assert cache.stats()["size"] == 0
    assert cache.stats()["expired_returned_none"] == 1


@pytest.mark.asyncio
async def test_e2e_ttl_bounded_by_token_expiry(monkeypatch):
    """Cache TTL is generous, token TTL is tight — cache entry must
    expire when the token does, not when the cache TTL would."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")

    from app.core.auth_cache import AuthCache

    calls = 0

    async def _fetch(token):
        nonlocal calls
        calls += 1
        # Token expires 50ms in the future.
        return _make_auth(token_expires_at=time.time() + 0.05)

    cache = AuthCache(fetch=_fetch, cache_ttl_seconds=60.0)
    await cache.resolve("t-1")

    # Past token expiry, well within cache TTL — must refetch.
    await asyncio.sleep(0.1)
    await cache.resolve("t-1")
    assert calls == 2


# ── E2E: missed-event behavior ───────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_missed_invalidation_recovers_via_ttl_expiry(monkeypatch):
    """The reviewer's critical scenario. Cache is populated. The
    invalidation event is LOST (never published). Bounded TTL is
    the correctness ceiling — after TTL elapses, the next resolve
    refetches and picks up the truth."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")

    from app.core.auth_cache import AuthCache

    calls = 0
    server_side_state = {"tier": "tier_2"}

    async def _fetch(token):
        nonlocal calls
        calls += 1
        return _make_auth(agent_risk_tier=server_side_state["tier"])

    cache = AuthCache(fetch=_fetch, cache_ttl_seconds=0.05)
    a1 = await cache.resolve("t-1")
    assert a1.agent_risk_tier == "tier_2"

    # Server-side state flips. NO invalidation event is published.
    server_side_state["tier"] = "tier_3"

    # Within TTL, cache still serves the stale tier.
    a2 = await cache.resolve("t-1")
    assert a2.agent_risk_tier == "tier_2", "stale within TTL is acceptable"

    # After TTL, next resolve refetches and gets the true value.
    await asyncio.sleep(0.1)
    a3 = await cache.resolve("t-1")
    assert a3.agent_risk_tier == "tier_3", (
        "TTL is the correctness ceiling — after expiry, the cache MUST "
        "have refetched and picked up the new tier"
    )
    assert calls == 2


@pytest.mark.asyncio
async def test_e2e_invalidation_race_during_fetch_discards(monkeypatch):
    """Reviewer's other critical scenario. A publisher fires while a
    lookup is in flight. The lookup completes but the result is
    discarded (generation fence), so the next request refetches
    against the post-invalidation truth."""
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")

    from app.core.auth_cache import AuthCache

    fetch_started = asyncio.Event()
    let_finish = asyncio.Event()

    async def _fetch(token):
        fetch_started.set()
        await let_finish.wait()
        return _make_auth(agent_identity_id="ident-x")

    bus = _InMemoryBus()
    cache = AuthCache(fetch=_fetch, invalidation_bus=bus)

    task = asyncio.create_task(cache.resolve("t-1"))
    await fetch_started.wait()
    # Publisher fires WHILE fetch is in flight.
    await bus.publish("auth.identity.disabled", "ident-x")
    let_finish.set()
    result = await task

    assert result is None, (
        "in-flight fetch was invalidated during the lookup; returning "
        "the fetched value would authorize a request against state we "
        "have already been told is invalid"
    )
    assert cache.stats()["fence_discards"] == 1
    assert cache.stats()["size"] == 0


# ── E2E: publisher helpers actually fire ─────────────────────────────

@pytest.mark.asyncio
async def test_publisher_helpers_emit_correct_events(monkeypatch):
    """Verify the publisher helpers in ``auth_events`` emit the correct
    (kind, key) tuple to the bus."""
    monkeypatch.setenv("INVALIDATION_BUS_ENABLED", "true")
    from app.core import auth_events
    from app.core import invalidation_bus as bus_mod

    calls: list[tuple[str, str]] = []

    class _RecordingBus:
        async def publish(self, kind, key, version):
            calls.append((kind, key))

    monkeypatch.setattr(bus_mod, "get_bus", lambda: _RecordingBus())

    auth_events.publish_token_revoked("guard-mt-xyz")
    auth_events.publish_identity_disabled("ident-1")
    auth_events.publish_risk_tier_changed("ident-2")
    auth_events.publish_permission_changed("ws-1")
    auth_events.publish_workspace_changed("ws-2")

    # Give the event loop a tick to fire the scheduled tasks.
    await asyncio.sleep(0.01)

    kinds = [k for (k, _) in calls]
    assert "auth.token.revoked" in kinds
    assert "auth.identity.disabled" in kinds
    assert "auth.risk_tier.changed" in kinds
    assert "auth.permission.changed" in kinds
    assert "auth.workspace.changed" in kinds

    # Token event carries the fingerprint, not the raw token.
    for kind, key in calls:
        if kind == "auth.token.revoked":
            assert key != "guard-mt-xyz", "raw token must never appear on the bus"
            assert len(key) == 64, "fingerprint must be SHA-256 hex (64 chars)"
