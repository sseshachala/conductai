"""In-process LRU cache for immutable Gateway v2 revision snapshots.

Slice 6a of the PR 6 (Redis-first hot path) rollout. This is the safest
possible cache: only the immutable revision content is cached, keyed
by the opaque ``revision_id`` UUID. Revisions never change once
published — a new revision gets a new ID and the profile's pointer
flips to it. So a cache entry is either correct or absent; it can
never be stale.

Explicit non-caches (per reviewer's slice 6a guidance):

- The **active-revision pointer** ``(workspace_id, cond_code) →
  revision_id`` is NOT cached here. That mapping is mutable — publish,
  rollback, and unpublish must be immediately effective. Callers still
  perform one DB read to get the pointer, then hit this cache for the
  snapshot content by ID.
- **Credentials** are never in the snapshot. ``Target.credential_ref``
  is a reference (e.g. ``vault://<env-uuid>/<name>``); the actual
  secret is resolved per request against Vault so revocations take
  effect on the next request.

Eviction is LRU with a bounded max entry count (env-tunable via
``GATEWAY_REVISION_CACHE_MAX``, default 100). Eviction is a memory
concern, not a correctness concern — immutability guarantees any
cached entry is still valid for as long as the process runs.

The cache is process-local. Cross-worker consistency is not required
because entries are immutable and callers always look up by the ID
they got from the fresh pointer read.
"""
from __future__ import annotations

import os
from collections import OrderedDict
from threading import RLock
from typing import Any
from uuid import UUID

import structlog

log = structlog.get_logger()


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


class _RevisionLRU:
    """Bounded, thread-safe LRU keyed by revision UUID.

    Values are the parsed ``GatewayProfileV2`` — Pydantic model,
    immutable by convention (extra="forbid"). We store the object
    directly; callers must not mutate it.
    """

    __slots__ = ("_cache", "_lock", "_max", "_hits", "_misses", "_evictions")

    def __init__(self, max_entries: int) -> None:
        self._cache: OrderedDict[UUID, Any] = OrderedDict()
        self._lock = RLock()
        self._max = max_entries
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, revision_id: UUID) -> Any | None:
        with self._lock:
            value = self._cache.get(revision_id)
            if value is not None:
                self._cache.move_to_end(revision_id)
                self._hits += 1
                return value
            self._misses += 1
            return None

    def put(self, revision_id: UUID, snapshot: Any) -> None:
        with self._lock:
            existing = self._cache.get(revision_id)
            if existing is not None:
                # Same ID → same immutable content by contract. Move
                # to MRU end; do not replace (defense against a caller
                # that constructed a slightly different Pydantic
                # instance for the same revision).
                self._cache.move_to_end(revision_id)
                return
            self._cache[revision_id] = snapshot
            while len(self._cache) > self._max:
                # Evict LRU.
                evicted_id, _ = self._cache.popitem(last=False)
                self._evictions += 1
                log.debug(
                    "gateway.revision_cache.evict",
                    revision_id=str(evicted_id),
                    size=len(self._cache),
                )

    def stats(self) -> dict[str, int]:
        with self._lock:
            total = self._hits + self._misses
            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "size": len(self._cache),
                "max": self._max,
                "hit_rate_bp": (
                    (10_000 * self._hits) // total if total else 0
                ),
            }

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            self._evictions = 0


_CACHE = _RevisionLRU(_env_int("GATEWAY_REVISION_CACHE_MAX", 100))


def get(revision_id: UUID) -> Any | None:
    """Return the cached ``GatewayProfileV2`` for the revision, or
    ``None`` on miss."""
    return _CACHE.get(revision_id)


def put(revision_id: UUID, snapshot: Any) -> None:
    """Populate the cache. Idempotent — same revision_id → same
    immutable content."""
    _CACHE.put(revision_id, snapshot)


def stats() -> dict[str, int]:
    """Snapshot of counters. Callable from /health or a debug endpoint."""
    return _CACHE.stats()


def clear() -> None:
    """Reset the cache. Test-only in production; useful in per-worker
    hot-reload scenarios (never called from the request path)."""
    _CACHE.clear()
