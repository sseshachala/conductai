"""Tiny per-process TTL cache for read-heavy aggregates where staleness is harmless.

ponytail: each worker warms its own copy. Move to Redis if workers scale out and
the extra cold misses show up. Never cache anything auth- or write-path related.
"""
from __future__ import annotations

import time
from typing import Any, Callable, Hashable


class TTLCache:
    def __init__(self, max_entries: int = 1000) -> None:
        self._max = max_entries
        self._data: dict[Hashable, tuple[float, Any]] = {}

    def get_or_compute(self, key: Hashable, ttl_s: float, compute: Callable[[], Any]) -> Any:
        hit = self._data.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        value = compute()
        if len(self._data) >= self._max:
            self._data.clear()
        self._data[key] = (time.monotonic() + ttl_s, value)
        return value

    def clear(self) -> None:
        self._data.clear()
