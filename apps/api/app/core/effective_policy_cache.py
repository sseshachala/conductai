"""PR 6c — in-process front-cache for ``compute_policy``.

Correctness comes from TTL + per-workspace generation counters. Bus
events (``guard.policy.invalidated`` / ``guard.pack.updated``) are a
fast-path signal; losing one is a latency regression, not a bug.

Threading model: ``compute_policy`` runs under ``run_in_threadpool``,
so all ops guard state with ``threading.Lock``. Bus handlers run on
the event loop and take the same lock.
"""
from __future__ import annotations

import copy
import os
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import structlog

from app.core.env_helpers import env_float, env_int

log = structlog.get_logger()


def _enabled() -> bool:
    return os.environ.get("EFFECTIVE_POLICY_CACHE_ENABLED", "false").lower() in (
        "1", "true", "yes",
    )


@dataclass
class _Entry:
    rules: list[dict]
    expires_at: float


@dataclass(frozen=True)
class Fence:
    """Generation snapshot at fetch start. A write must observe the
    same counters at put time — otherwise an invalidation raced ahead
    of the build and the fetched value is already known stale."""
    workspace_gen: int
    global_gen: int


class EffectivePolicyCache:
    def __init__(
        self,
        *,
        ttl_seconds: float | None = None,
        max_entries: int | None = None,
    ) -> None:
        self._ttl = ttl_seconds if ttl_seconds is not None else env_float(
            "EFFECTIVE_POLICY_CACHE_TTL_SECONDS", 30.0,
        )
        self._max = max_entries if max_entries is not None else env_int(
            "EFFECTIVE_POLICY_CACHE_MAX_ENTRIES", 10_000, minimum=0,
        )
        self._entries: dict[tuple[str, str], _Entry] = {}
        self._gen_by_workspace: dict[str, int] = defaultdict(int)
        self._gen_global: int = 0
        self._lock = threading.Lock()
        self._hits = 0
        self._misses = 0
        self._fence_discards = 0
        self._invalidations_workspace = 0
        self._invalidations_all = 0
        self._bus_events_handled = 0

    def get(self, workspace_id: Any, persona: str) -> list[dict] | None:
        if not _enabled() or self._max <= 0:
            return None
        key = (str(workspace_id), persona)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            if time.monotonic() > entry.expires_at:
                del self._entries[key]
                self._misses += 1
                return None
            self._hits += 1
            return copy.deepcopy(entry.rules)

    def capture_fence(self, workspace_id: Any) -> Fence:
        with self._lock:
            return Fence(
                workspace_gen=self._gen_by_workspace.get(str(workspace_id), 0),
                global_gen=self._gen_global,
            )

    def put_if_fresh(
        self, workspace_id: Any, persona: str, rules: list[dict], fence: Fence,
    ) -> bool:
        if not _enabled() or self._max <= 0:
            return False
        ws_key = str(workspace_id)
        with self._lock:
            if (self._gen_by_workspace.get(ws_key, 0) != fence.workspace_gen
                    or self._gen_global != fence.global_gen):
                self._fence_discards += 1
                return False
            if len(self._entries) >= self._max:
                # Evict by earliest expiry — hot entries survive under pressure
                # without LRU bookkeeping. ponytail: swap for LRU if hit rate suffers.
                oldest = min(self._entries.items(), key=lambda kv: kv[1].expires_at)
                del self._entries[oldest[0]]
            self._entries[(ws_key, persona)] = _Entry(
                rules=copy.deepcopy(rules),
                expires_at=time.monotonic() + self._ttl,
            )
            return True

    def invalidate_workspace(self, workspace_id: Any) -> None:
        ws_key = str(workspace_id)
        with self._lock:
            self._gen_by_workspace[ws_key] = self._gen_by_workspace.get(ws_key, 0) + 1
            for k in [k for k in self._entries if k[0] == ws_key]:
                del self._entries[k]
            self._invalidations_workspace += 1

    def invalidate_all(self) -> None:
        with self._lock:
            self._gen_global += 1
            self._entries.clear()
            self._invalidations_all += 1

    def attach_bus(self, bus: Any) -> None:
        async def _on_policy_invalidated(event: dict) -> None:
            self.invalidate_workspace(event.get("key", ""))
            with self._lock:
                self._bus_events_handled += 1

        async def _on_pack_updated(event: dict) -> None:
            self.invalidate_all()
            with self._lock:
                self._bus_events_handled += 1

        bus.subscribe(["guard.policy.invalidated"], _on_policy_invalidated)
        bus.subscribe(["guard.pack.updated"], _on_pack_updated)

    def stats(self) -> dict:
        with self._lock:
            return {
                "enabled": _enabled(),
                "size": len(self._entries),
                "hits": self._hits,
                "misses": self._misses,
                "fence_discards": self._fence_discards,
                "invalidations_workspace": self._invalidations_workspace,
                "invalidations_all": self._invalidations_all,
                "bus_events_handled": self._bus_events_handled,
                "gen_global": self._gen_global,
            }


_INSTANCE: EffectivePolicyCache | None = None


def init_effective_policy_cache(
    *,
    ttl_seconds: float | None = None,
    max_entries: int | None = None,
) -> EffectivePolicyCache:
    """FastAPI startup entry: create the process-global cache and
    attach it to the invalidation bus (best-effort)."""
    global _INSTANCE
    _INSTANCE = EffectivePolicyCache(ttl_seconds=ttl_seconds, max_entries=max_entries)
    try:
        from app.core.invalidation_bus import get_bus
        _INSTANCE.attach_bus(get_bus())
    except Exception as e:  # noqa: BLE001
        log.warning("effective_policy_cache.bus_attach_failed", err=str(e))
    return _INSTANCE


def get_effective_policy_cache() -> EffectivePolicyCache:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = EffectivePolicyCache()
    return _INSTANCE


def reset_effective_policy_cache_for_tests() -> None:
    global _INSTANCE
    _INSTANCE = None
