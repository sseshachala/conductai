"""Slice 6b — auth cache. Bounded-stale resolution of Bearer tokens
into their authorization tuple, keyed by token fingerprint.

Correctness contract every consumer must uphold:

1. **Fingerprint keying.** Cache keys are SHA-256 hashes of the token
   bytes. Raw tokens are NEVER stored anywhere in the cache. A cache
   dump / log leak / snapshot cannot exfiltrate the bearer credential.

2. **TTL = min(cache_ttl, token_ttl).** A cache entry can NEVER
   outlive the token it authorizes. If the token expires in 30s and
   the cache TTL is 60s, the entry expires in 30s.

3. **Invalidation triggers.** The invalidation bus (PR 6e) publishes
   events on every server-side auth change; this cache subscribes to
   ALL of them, not just token revocation:

   - ``auth.token.revoked`` — one specific token gone.
   - ``auth.identity.disabled`` — every token for this identity gone.
   - ``auth.risk_tier.changed`` — every token for this identity gone.
   - ``auth.permission.changed`` — every token for this workspace
     gone (permission scope can be workspace-wide).
   - ``auth.workspace.changed`` — every token for this workspace
     gone (membership + workspace config).

4. **Bounded staleness (default 60s — not a recommendation).** If a
   bus message is lost entirely, worst-case a revoked credential
   remains usable for up to ``cache_ttl_seconds``. Configurable via
   ``AUTH_CACHE_TTL_SECONDS`` env var. Deployments MUST explicitly
   approve their chosen revocation window — 60s is only a starting
   value, not a security-approved default. A shorter window (e.g.
   10s) is appropriate for higher-security surfaces; longer values
   should be justified and documented.

5. **Single-flight resolve.** N concurrent requests with the same
   fingerprint on a cold cache trigger exactly one fetch. Others
   wait; each re-checks the cache after the winner populates.

6. **Generation fencing on in-flight lookups.** Every invalidation
   bumps a per-dimension generation counter (fingerprint, identity,
   workspace, global). A fetch that started before an invalidation
   fires MUST discard its result — otherwise the returned value can
   authorize a request against state that was just invalidated. The
   cache captures generations at fetch start and re-checks all four
   dimensions before storing/returning.

7. **Expired tokens are rejected, not returned.** If the fetch
   returns an auth record whose ``token_expires_at`` is already in
   the past, ``resolve()`` returns ``None`` (authentication failure)
   rather than the auth record — a caller must never authorize a
   request against an expired token even if the fetch happened to
   produce one.

8. **Kill switch.** ``AUTH_CACHE_ENABLED=false`` (default) disables
   the cache entirely — every call falls through to ``fetch``.
   Deploy with the switch OFF, flip after canary validation, flip
   OFF to roll back.

Not in this module:

- The DB writer path that publishes invalidation events. That's a
  companion commit — every place that revokes / disables / changes
  permissions / bumps risk-tier calls ``invalidation_bus.publish``.
- Wiring into gateway / MCP request paths. Separate commit once
  this module is reviewed.
- Budget reservations. Those need atomic accounting (PR 6d), not
  bounded-stale reads.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import structlog

log = structlog.get_logger()


@dataclass(frozen=True)
class CachedAuth:
    """Resolved auth for a token. Immutable. Never contains the raw
    bearer credential — the cache stores the fingerprint separately
    as the key and the resolved tuple as the value."""

    workspace_id: str
    clerk_user_id: str | None
    agent_identity_id: str | None
    agent_risk_tier: str | None
    is_internal: bool
    token_expires_at: float | None  # epoch seconds; None = non-expiring


FetchFn = Callable[[str], "Awaitable[CachedAuth | None]"]


def _fingerprint(token: str) -> str:
    """SHA-256 hex of the token bytes. This is the cache key. The raw
    token never leaves the caller's scope."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _enabled() -> bool:
    return os.environ.get("AUTH_CACHE_ENABLED", "false").lower() in (
        "1",
        "true",
        "yes",
    )


def _ttl_default() -> float:
    raw = os.environ.get("AUTH_CACHE_TTL_SECONDS")
    if not raw:
        return 60.0
    try:
        return max(1.0, float(raw))
    except ValueError:
        return 60.0


@dataclass
class _Entry:
    auth: CachedAuth
    expires_at: float  # monotonic seconds — min(cache_ttl, token_ttl)


@dataclass
class _KeyLock:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    refcount: int = 0


class AuthCache:
    """See module docstring for the correctness contract.

    Callers use ``resolve(token)`` to get a ``CachedAuth``. The cache
    handles fingerprint derivation, TTL bounding, single-flight, and
    invalidation subscription. Callers must NOT bypass the cache when
    it's enabled — that would defeat the invalidation-fence guarantees.
    """

    def __init__(
        self,
        *,
        fetch: FetchFn,
        cache_ttl_seconds: float | None = None,
        invalidation_bus: Any | None = None,
        max_entries: int = 100_000,
    ) -> None:
        self._fetch = fetch
        self._ttl = cache_ttl_seconds if cache_ttl_seconds is not None else _ttl_default()
        self._max = max_entries
        self._entries: dict[str, _Entry] = {}
        # Secondary indices for multi-key invalidation. Maintained
        # eagerly on populate, cleaned lazily on invalidate.
        self._by_identity: dict[str, set[str]] = {}
        self._by_workspace: dict[str, set[str]] = {}
        self._locks: dict[str, _KeyLock] = {}
        # Generation counters for in-flight fence. Bumped on every
        # invalidation. A fetch captures the pre-fetch values at
        # start; if any bumped by fetch end, the result is discarded.
        self._fp_gens: dict[str, int] = {}
        self._identity_gens: dict[str, int] = {}
        self._workspace_gens: dict[str, int] = {}
        self._global_gen: int = 0
        # Stats.
        self._hits = 0
        self._misses = 0
        self._negative_hits = 0  # cached "no auth" (fetch returned None)
        self._invalidations_token = 0
        self._invalidations_identity = 0
        self._invalidations_workspace = 0
        self._evictions = 0
        self._bus_events_handled = 0
        self._fence_discards = 0
        self._expired_returned_none = 0

        if invalidation_bus is not None:
            self._subscribe(invalidation_bus)

    # ── Public API ────────────────────────────────────────────────

    async def resolve(self, token: str) -> CachedAuth | None:
        """Resolve a token to its ``CachedAuth`` or ``None`` if the
        token is unknown / invalid.

        Kill switch (``AUTH_CACHE_ENABLED=false``): bypasses the cache
        entirely; every call goes to the fetch function.
        """
        if not _enabled():
            return await self._fetch(token)

        fp = _fingerprint(token)
        entry = self._entries.get(fp)
        now = time.monotonic()
        if entry is not None and entry.expires_at > now:
            self._hits += 1
            return entry.auth

        self._misses += 1

        async with self._key_lock_ctx(fp):
            # Recheck after acquiring lock — winner may have populated.
            entry = self._entries.get(fp)
            now = time.monotonic()
            if entry is not None and entry.expires_at > now:
                return entry.auth

            # Capture generations BEFORE the fetch. Bumped values by
            # fetch-completion time mean an invalidation raced with
            # us; we discard the fetched result to avoid authorizing
            # against just-invalidated state.
            fp_gen_start = self._fp_gens.get(fp, 0)
            global_gen_start = self._global_gen
            identity_gens_start = dict(self._identity_gens)
            workspace_gens_start = dict(self._workspace_gens)

            auth = await self._fetch(token)
            if auth is None:
                # Do NOT cache the negative. A token that's currently
                # unknown may become known momentarily (e.g. tail-end
                # of a signup flow) — caching would trap the client
                # for the full TTL. Fall through to fetch again.
                self._negative_hits += 1
                return None

            # ── Generation fence — P1 review fix ────────────────
            # Check every dimension. If any bumped during fetch, the
            # fetched result reflects state we've been told is stale.
            # Discard, return None (authentication failure). Caller
            # falls through to next request which will refetch.
            if self._fp_gens.get(fp, 0) != fp_gen_start:
                self._fence_discards += 1
                return None
            if self._global_gen != global_gen_start:
                # A global-scope invalidation fired. Check whether the
                # specific identity/workspace this auth points at was
                # affected.
                if auth.agent_identity_id and self._identity_gens.get(
                    auth.agent_identity_id, 0
                ) != identity_gens_start.get(auth.agent_identity_id, 0):
                    self._fence_discards += 1
                    return None
                if auth.workspace_id and self._workspace_gens.get(
                    auth.workspace_id, 0
                ) != workspace_gens_start.get(auth.workspace_id, 0):
                    self._fence_discards += 1
                    return None
                # global gen bumped but neither this identity nor
                # workspace is affected — proceed. (e.g. invalidation
                # of a different tenant.)

            # ── Expired-token defense — P1 review fix ────────────
            # If the fetch returned an auth record whose token is
            # already expired, reject it. Caller must NEVER authorize
            # a request against an expired token, even if the fetch
            # happened to produce one.
            token_ttl_remaining = (
                (auth.token_expires_at - time.time())
                if auth.token_expires_at is not None
                else None
            )
            if token_ttl_remaining is not None and token_ttl_remaining <= 0:
                self._expired_returned_none += 1
                return None

            # TTL bounded by both cache TTL and token expiry.
            cache_expires_at = now + self._ttl
            if token_ttl_remaining is not None:
                token_expires_at_monotonic = now + token_ttl_remaining
                effective_expires_at = min(
                    cache_expires_at, token_expires_at_monotonic
                )
            else:
                effective_expires_at = cache_expires_at

            self._entries[fp] = _Entry(auth=auth, expires_at=effective_expires_at)
            # Secondary indices for multi-key invalidation.
            if auth.agent_identity_id:
                self._by_identity.setdefault(auth.agent_identity_id, set()).add(fp)
            if auth.workspace_id:
                self._by_workspace.setdefault(auth.workspace_id, set()).add(fp)

            # Bounded size — oldest expires_at evicted.
            if len(self._entries) > self._max:
                oldest_fp = min(
                    self._entries.items(),
                    key=lambda kv: kv[1].expires_at,
                )[0]
                self._drop_fingerprint(oldest_fp)
                self._evictions += 1

            return auth

    def invalidate_token(self, token: str) -> None:
        """Drop cache entry for one specific token. Bump per-fingerprint
        and global generation so an in-flight fetch for the same
        fingerprint discards its result. Idempotent."""
        fp = _fingerprint(token)
        self._fp_gens[fp] = self._fp_gens.get(fp, 0) + 1
        self._global_gen += 1
        if self._drop_fingerprint(fp):
            self._invalidations_token += 1

    def invalidate_fingerprint(self, fp: str) -> None:
        """Drop cache entry by fingerprint (bus events carry fingerprints,
        not raw tokens). Bumps generation counters like ``invalidate_token``."""
        self._fp_gens[fp] = self._fp_gens.get(fp, 0) + 1
        self._global_gen += 1
        if self._drop_fingerprint(fp):
            self._invalidations_token += 1

    def invalidate_identity(self, agent_identity_id: str) -> None:
        """Drop every cache entry for an agent identity. Used on
        identity disable + risk-tier change events. Bumps identity
        generation so in-flight fetches whose result points at this
        identity discard themselves."""
        self._identity_gens[agent_identity_id] = (
            self._identity_gens.get(agent_identity_id, 0) + 1
        )
        self._global_gen += 1
        fps = self._by_identity.pop(agent_identity_id, set())
        for fp in list(fps):
            self._drop_fingerprint(fp, skip_identity_cleanup=True)
        if fps:
            self._invalidations_identity += 1

    def invalidate_workspace(self, workspace_id: str) -> None:
        """Drop every cache entry for a workspace. Used on
        permission / membership / workspace-config change events.
        Bumps workspace generation so in-flight fetches for this
        workspace discard themselves."""
        self._workspace_gens[workspace_id] = (
            self._workspace_gens.get(workspace_id, 0) + 1
        )
        self._global_gen += 1
        fps = self._by_workspace.pop(workspace_id, set())
        for fp in list(fps):
            self._drop_fingerprint(fp, skip_workspace_cleanup=True)
        if fps:
            self._invalidations_workspace += 1

    def invalidate_all(self) -> None:
        """Drop the whole cache. Bumps the global generation so every
        in-flight fetch discards itself. Nuclear option — use sparingly."""
        self._global_gen += 1
        n = len(self._entries)
        self._entries.clear()
        self._by_identity.clear()
        self._by_workspace.clear()
        self._invalidations_token += n

    def stats(self) -> dict[str, Any]:
        total = self._hits + self._misses
        return {
            "enabled": _enabled(),
            "size": len(self._entries),
            "max": self._max,
            "ttl_seconds": self._ttl,
            "hits": self._hits,
            "misses": self._misses,
            "negative_hits": self._negative_hits,
            "invalidations_token": self._invalidations_token,
            "invalidations_identity": self._invalidations_identity,
            "invalidations_workspace": self._invalidations_workspace,
            "evictions": self._evictions,
            "bus_events_handled": self._bus_events_handled,
            "fence_discards": self._fence_discards,
            "expired_returned_none": self._expired_returned_none,
            "active_locks": len(self._locks),
            "identity_index_size": len(self._by_identity),
            "workspace_index_size": len(self._by_workspace),
            "hit_rate_bp": (10_000 * self._hits) // total if total else 0,
        }

    # ── Internals ─────────────────────────────────────────────────

    @asynccontextmanager
    async def _key_lock_ctx(self, fp: str):
        """Refcount + async lock per fingerprint — same shape as
        ``VersionedCache._key_lock_ctx``. Prevents unbounded lock
        table growth on high-cardinality token workloads."""
        kl = self._locks.get(fp)
        if kl is None:
            kl = _KeyLock()
            self._locks[fp] = kl
        kl.refcount += 1
        try:
            async with kl.lock:
                yield
        finally:
            kl.refcount -= 1
            if kl.refcount <= 0:
                current = self._locks.get(fp)
                if current is kl:
                    self._locks.pop(fp, None)

    def _drop_fingerprint(
        self,
        fp: str,
        *,
        skip_identity_cleanup: bool = False,
        skip_workspace_cleanup: bool = False,
    ) -> bool:
        """Drop an entry + clean secondary indices. Returns True if
        the entry existed."""
        entry = self._entries.pop(fp, None)
        if entry is None:
            return False
        if not skip_identity_cleanup and entry.auth.agent_identity_id:
            idx = self._by_identity.get(entry.auth.agent_identity_id)
            if idx is not None:
                idx.discard(fp)
                if not idx:
                    self._by_identity.pop(entry.auth.agent_identity_id, None)
        if not skip_workspace_cleanup and entry.auth.workspace_id:
            idx = self._by_workspace.get(entry.auth.workspace_id)
            if idx is not None:
                idx.discard(fp)
                if not idx:
                    self._by_workspace.pop(entry.auth.workspace_id, None)
        return True

    def _subscribe(self, bus: Any) -> None:
        """Register bus handlers for every event kind that can
        invalidate an auth entry. Idempotent handlers — they may be
        called multiple times for the same event (bus + periodic
        refresh + startup replay)."""

        async def _on_token_revoked(event: dict) -> None:
            self._bus_events_handled += 1
            key = event.get("key")
            if key:
                # Bus events carry the FINGERPRINT, not the raw token.
                self.invalidate_fingerprint(key)

        async def _on_identity_disabled(event: dict) -> None:
            self._bus_events_handled += 1
            key = event.get("key")
            if key:
                self.invalidate_identity(key)

        async def _on_risk_tier_changed(event: dict) -> None:
            self._bus_events_handled += 1
            key = event.get("key")
            if key:
                self.invalidate_identity(key)

        async def _on_permission_changed(event: dict) -> None:
            self._bus_events_handled += 1
            key = event.get("key")
            if key:
                self.invalidate_workspace(key)

        async def _on_workspace_changed(event: dict) -> None:
            self._bus_events_handled += 1
            key = event.get("key")
            if key:
                self.invalidate_workspace(key)

        bus.subscribe(["auth.token.revoked"], _on_token_revoked)
        bus.subscribe(["auth.identity.disabled"], _on_identity_disabled)
        bus.subscribe(["auth.risk_tier.changed"], _on_risk_tier_changed)
        bus.subscribe(["auth.permission.changed"], _on_permission_changed)
        bus.subscribe(["auth.workspace.changed"], _on_workspace_changed)
