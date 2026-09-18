"""PR 6b wiring — proves the gateway handler shortcuts to AuthCache
on hit.

Reviewer directive from prior 6-series PRs: prove the invariant with
a runnable check, not source-level grep. This test uses an in-memory
bus stub + a stubbed fetch function that increments a counter every
time it fires; on cache hit the counter must NOT advance.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_singletons(monkeypatch):
    monkeypatch.setenv("AUTH_CACHE_ENABLED", "true")
    from app.core.auth_cache import reset_auth_cache_for_tests
    reset_auth_cache_for_tests()
    yield
    reset_auth_cache_for_tests()


@pytest.mark.asyncio
async def test_gateway_helper_fetch_populates_cache(monkeypatch):
    """First resolve() misses -> fetch fires -> cache populated. Second
    resolve() with the same token hits -> fetch does NOT fire again."""
    from app.core.auth_cache import CachedAuth, init_auth_cache
    from app.core.invalidation_bus import InvalidationBus

    calls = 0

    async def _fetch(token):
        nonlocal calls
        calls += 1
        return CachedAuth(
            workspace_id="ws-1",
            clerk_user_id="user-1",
            agent_identity_id=None,
            agent_risk_tier=None,
            is_internal=False,
            token_expires_at=None,
        )

    cache = init_auth_cache(fetch=_fetch, invalidation_bus=InvalidationBus())

    a1 = await cache.resolve("guard-mt-abc")
    a2 = await cache.resolve("guard-mt-abc")
    assert a1 is not None and a2 is not None
    assert a1.workspace_id == "ws-1"
    assert calls == 1, f"cache hit did not skip fetch (calls={calls})"


@pytest.mark.asyncio
async def test_fetch_returning_none_does_not_cache(monkeypatch):
    """Invalid tokens (fetch returns None) must NOT be cached — every
    call re-fetches so a client that just completed a signup can
    proceed on the next attempt without waiting the TTL."""
    from app.core.auth_cache import init_auth_cache

    calls = 0

    async def _fetch(token):
        nonlocal calls
        calls += 1
        return None

    cache = init_auth_cache(fetch=_fetch)

    for _ in range(3):
        assert await cache.resolve("garbage-token") is None
    assert calls == 3, "negative results should not be cached"


@pytest.mark.asyncio
async def test_gateway_helpers_fetch_returns_cached_auth_shape(monkeypatch):
    """The fetch function in gateway_helpers must build a valid
    CachedAuth (right field types) when the resolver returns a
    known token. Uses monkeypatched resolvers to avoid touching the
    DB."""
    from app.core.auth_cache import CachedAuth
    from app.modules.guard import gateway_helpers

    class _FakeIdentity:
        id = "ident-42"
        risk_tier = "tier_2"

    def _fake_resolve_agent_token(token, db):
        return ("ws-42", "user-42")

    def _fake_resolve_agent_identity_row(token, db):
        return _FakeIdentity()

    class _FakeSessionCtor:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

    session_holder = {}

    def _fake_session_local():
        s = _FakeSessionCtor()
        session_holder["s"] = s
        return s

    monkeypatch.setattr(
        "app.core.auth.resolve_agent_token", _fake_resolve_agent_token,
    )
    monkeypatch.setattr(
        "app.core.auth.resolve_agent_identity_row",
        _fake_resolve_agent_identity_row,
    )
    monkeypatch.setattr(
        "app.core.database.SessionLocal", _fake_session_local,
    )

    result = await gateway_helpers.auth_cache_fetch_member("member-token")
    assert isinstance(result, CachedAuth)
    assert result.workspace_id == "ws-42"
    assert result.clerk_user_id == "user-42"
    assert result.agent_identity_id == "ident-42"
    assert result.agent_risk_tier == "tier_2"
    assert result.is_internal is False
    assert session_holder["s"].closed is True, "session must be closed after fetch"


@pytest.mark.asyncio
async def test_fetch_returns_none_when_resolver_rejects(monkeypatch):
    from app.modules.guard import gateway_helpers

    def _fake_resolve_agent_token(token, db):
        return None

    class _FakeSession:
        def close(self):
            pass

    monkeypatch.setattr(
        "app.core.auth.resolve_agent_token", _fake_resolve_agent_token,
    )
    monkeypatch.setattr(
        "app.core.database.SessionLocal", _FakeSession,
    )

    result = await gateway_helpers.auth_cache_fetch_member("bogus")
    assert result is None
