"""Budget ledger sync Redis client (shared pool, bounded timeouts).

Extracted from ``budget_ledger.py`` (pure move, no behavior change);
``app.core.budget_ledger`` remains the public facade.
"""
from __future__ import annotations

import os

import redis as _redis_sync


# ── Redis client (sync, shared pool) ────────────────────────────────

_pool: _redis_sync.ConnectionPool | None = None


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379")


# R3 fix (reviewer P1): bounded socket timeouts so a Redis blip does
# not hang the gateway thread pool indefinitely. Defaults are
# deliberately short (2s) because the ledger sits on the request
# critical path — a slow Redis is materially worse than a hard fail
# that the caller can classify as REDIS_DOWN and reject.
_REDIS_SOCKET_TIMEOUT_SEC = float(
    os.environ.get("BUDGET_LEDGER_REDIS_SOCKET_TIMEOUT_SEC", "2.0")
)
_REDIS_CONNECT_TIMEOUT_SEC = float(
    os.environ.get("BUDGET_LEDGER_REDIS_CONNECT_TIMEOUT_SEC", "1.5")
)


def _r() -> _redis_sync.Redis:
    global _pool
    if _pool is None:
        _pool = _redis_sync.ConnectionPool.from_url(
            _redis_url(),
            decode_responses=True,
            socket_timeout=_REDIS_SOCKET_TIMEOUT_SEC,
            socket_connect_timeout=_REDIS_CONNECT_TIMEOUT_SEC,
        )
    return _redis_sync.Redis(connection_pool=_pool)


def _reset_pool_for_tests() -> None:
    global _pool
    _pool = None
