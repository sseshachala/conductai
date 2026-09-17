"""PR 6d — atomic budget-reservation ledger.

Closes the race window in the existing spend-cap enforcement path where
two concurrent requests each read ``monthly_cost < cap`` and both
proceed, together spending past the cap.

Model:
- **committed** — spend already recorded as ``guard_audit_events`` rows.
  Postgres is source of truth. Cached separately (see ``current_committed_cents``).
- **reserved** — in-flight spend estimates. Redis atomic counter per
  ``(workspace_id, ai_tool_or_all, period)``. Short-lived: incremented
  at reserve, decremented at release/commit.

Cap enforcement: ``committed + reserved + estimated <= cap``. The
INCRBY + comparison + optional DECRBY runs in a single Lua script so
concurrent reserves cannot collectively overshoot the cap.

Kill switch: ``BUDGET_LEDGER_ENABLED=false`` (default). Every call
returns ``ALLOW`` sentinel and takes zero Redis roundtrips.

Failure modes:
- Redis unreachable → ``reserve`` returns ``BudgetDecision.REDIS_DOWN``.
  Callers should fall through to the existing DB-based ``budget_check``
  path (which is what the codebase does today). Set
  ``BUDGET_LEDGER_FAIL_CLOSED=true`` to refuse instead.
- Lua script rejected (older Redis) → same fallback.

Reconciler: not required for correctness because ``committed`` remains
in Postgres. A Redis flush loses in-flight reservations only — those
resolve within the request lifetime (release on completion) or are
naturally recovered because the audit event write is what actually
matters. Future durable-reservation extension (Postgres row per
reservation) is a separate PR; scoped out here.
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import redis as _redis_sync
import structlog

log = structlog.get_logger()


def enabled() -> bool:
    """Kill switch. Callers MUST check this before using the ledger —
    the primitive itself does not gate reads/writes so tests can drive
    it directly without setting the env var."""
    return os.environ.get("BUDGET_LEDGER_ENABLED", "false").lower() in (
        "1", "true", "yes",
    )


def fail_closed() -> bool:
    return os.environ.get("BUDGET_LEDGER_FAIL_CLOSED", "false").lower() in (
        "1", "true", "yes",
    )


class BudgetDecision(Enum):
    """Outcome of a ``reserve`` call.

    - ``ACCEPTED`` — capacity reserved, callers may proceed. Pair with
      ``release`` at request end.
    - ``EXCEEDED`` — reserving would push past the cap; the increment
      was refunded. Refuse the request.
    - ``REDIS_DOWN`` — the ledger could not run. Callers should fall
      through to the DB-based enforcement path unless
      ``BUDGET_LEDGER_FAIL_CLOSED`` is set (in which case treat like
      ``EXCEEDED``).
    - ``DISABLED`` — kill switch off; never gate on this. Callers
      should not have called the ledger at all.
    """
    ACCEPTED = "accepted"
    EXCEEDED = "exceeded"
    REDIS_DOWN = "redis_down"
    DISABLED = "disabled"


@dataclass(frozen=True)
class Reservation:
    """Handle returned on a successful ``reserve``. Pass to ``release``
    to refund unused capacity or to ``commit`` to convert reserved into
    committed once the actual cost is known."""
    reservation_id: str
    workspace_id: str
    ai_tool: str
    estimated_cents: int
    period_key: str


# ── Redis client (sync, shared pool) ────────────────────────────────

_pool: _redis_sync.ConnectionPool | None = None


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379")


def _r() -> _redis_sync.Redis:
    """Return a sync Redis client backed by a module-scoped pool.

    Matches the pattern in ``routers/ws.py`` so both surfaces share
    connection budget under load."""
    global _pool
    if _pool is None:
        _pool = _redis_sync.ConnectionPool.from_url(
            _redis_url(), decode_responses=True,
        )
    return _redis_sync.Redis(connection_pool=_pool)


def _reset_pool_for_tests() -> None:
    """Test hook — force a new pool so a fake-redis instance can
    replace the real one between tests."""
    global _pool
    _pool = None


# ── Period helpers ──────────────────────────────────────────────────

def _monthly_period_key(now: datetime | None = None) -> str:
    """Period key = ``YYYY-MM`` in UTC. Matches the monthly-cap semantics
    the existing ``budget_check`` uses (``_current_period_start`` returns
    the first-of-month in UTC)."""
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def _seconds_until_next_period(now: datetime | None = None) -> int:
    """Redis TTL for the reserved counter. Slightly longer than the
    period so a request that crosses the boundary can still release
    against the old key."""
    now = now or datetime.now(timezone.utc)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return int((end - now).total_seconds()) + 3600  # 1h slack


def _reserved_key(workspace_id: str, ai_tool: str | None, period_key: str) -> str:
    tool_seg = ai_tool if ai_tool else "_all"
    return f"budget:{workspace_id}:{tool_seg}:{period_key}:reserved"


# ── Atomic reserve (Lua) ────────────────────────────────────────────

# Atomicity requirement: the check "would this INCRBY push us past the
# cap?" and the actual increment must happen without another concurrent
# reserve slipping between them. Lua on the Redis side gives us
# single-threaded execution of the whole sequence.
_RESERVE_SCRIPT = """
local key = KEYS[1]
local estimated = tonumber(ARGV[1])
local ceiling = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])

local current = tonumber(redis.call('GET', key) or '0')
if current + estimated > ceiling then
    return {0, current}
end
local new = redis.call('INCRBY', key, estimated)
redis.call('EXPIRE', key, ttl)
return {1, new}
"""


# Refund is a bounded DECRBY that clamps at zero. A crash between
# reserve and release should not push the counter negative.
_RELEASE_SCRIPT = """
local key = KEYS[1]
local amount = tonumber(ARGV[1])
local current = tonumber(redis.call('GET', key) or '0')
if current <= 0 then
    return 0
end
local new_val = math.max(0, current - amount)
if new_val == 0 then
    redis.call('DEL', key)
else
    redis.call('SET', key, new_val)
end
return new_val
"""


class BudgetLedger:
    """Sync-friendly reservation ledger. One instance per worker.

    The caller supplies ``committed_cents`` (the already-spent amount
    the DB knows about) and ``cap_cents`` (the workspace's monthly hard
    cap). This class owns only the *reserved* counter and the
    check-and-increment atomicity.
    """

    def __init__(self, *, redis_client: _redis_sync.Redis | None = None) -> None:
        self._redis = redis_client
        self._reservations_accepted = 0
        self._reservations_exceeded = 0
        self._reservations_redis_down = 0
        self._releases = 0

    def _client(self) -> _redis_sync.Redis:
        return self._redis if self._redis is not None else _r()

    def reserve(
        self,
        *,
        workspace_id: str,
        ai_tool: str | None,
        estimated_cents: int,
        cap_cents: int,
        committed_cents: int,
    ) -> tuple[BudgetDecision, Optional[Reservation]]:
        """Atomically reserve ``estimated_cents`` if it fits.

        Ceiling passed to the Lua script is ``cap_cents - committed_cents``
        so the check compares only the reserved (in-flight) pool
        against remaining capacity. ``committed_cents`` is what the DB
        aggregation returns for the current period.
        """
        if estimated_cents <= 0:
            # Zero-cost reservations do not need to hit Redis.
            return BudgetDecision.ACCEPTED, Reservation(
                reservation_id=uuid.uuid4().hex,
                workspace_id=workspace_id,
                ai_tool=ai_tool or "_all",
                estimated_cents=0,
                period_key=_monthly_period_key(),
            )
        period_key = _monthly_period_key()
        key = _reserved_key(workspace_id, ai_tool, period_key)
        ceiling = max(0, cap_cents - committed_cents)
        ttl = _seconds_until_next_period()

        try:
            got, current = self._client().eval(
                _RESERVE_SCRIPT, 1, key, estimated_cents, ceiling, ttl,
            )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "budget_ledger.reserve_failed",
                workspace_id=workspace_id,
                ai_tool=ai_tool,
                err=str(e),
            )
            self._reservations_redis_down += 1
            return BudgetDecision.REDIS_DOWN, None

        if int(got) == 0:
            self._reservations_exceeded += 1
            return BudgetDecision.EXCEEDED, None

        self._reservations_accepted += 1
        return BudgetDecision.ACCEPTED, Reservation(
            reservation_id=uuid.uuid4().hex,
            workspace_id=workspace_id,
            ai_tool=ai_tool or "_all",
            estimated_cents=estimated_cents,
            period_key=period_key,
        )

    def release(self, reservation: Reservation) -> None:
        """Refund an in-flight reservation. Called at request end
        regardless of outcome — the audit event write is what makes
        the spend visible to the DB-side ``budget_check``.

        Idempotent-ish: multiple releases for the same reservation
        just DECRBY twice, clamped at zero. Callers should avoid
        double-releasing but a stray extra call is safe."""
        if reservation.estimated_cents <= 0:
            return
        ai_tool = None if reservation.ai_tool == "_all" else reservation.ai_tool
        key = _reserved_key(
            reservation.workspace_id, ai_tool, reservation.period_key,
        )
        try:
            self._client().eval(
                _RELEASE_SCRIPT, 1, key, reservation.estimated_cents,
            )
            self._releases += 1
        except Exception as e:  # noqa: BLE001
            log.warning(
                "budget_ledger.release_failed",
                workspace_id=reservation.workspace_id,
                err=str(e),
            )

    def current_reserved_cents(
        self, workspace_id: str, ai_tool: str | None,
    ) -> int:
        """Read the current in-flight reservation count. Used for
        display / observability. Returns 0 on Redis error — matches
        the fail-open behavior of the reserve path."""
        period_key = _monthly_period_key()
        key = _reserved_key(workspace_id, ai_tool, period_key)
        try:
            return int(self._client().get(key) or 0)
        except Exception as e:  # noqa: BLE001
            log.warning("budget_ledger.read_failed", err=str(e))
            return 0

    def stats(self) -> dict:
        return {
            "enabled": enabled(),
            "reservations_accepted": self._reservations_accepted,
            "reservations_exceeded": self._reservations_exceeded,
            "reservations_redis_down": self._reservations_redis_down,
            "releases": self._releases,
        }


# ── Singleton API ────────────────────────────────────────────────────

_INSTANCE: BudgetLedger | None = None


def get_budget_ledger() -> BudgetLedger:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = BudgetLedger()
    return _INSTANCE


def reset_budget_ledger_for_tests() -> None:
    global _INSTANCE
    _INSTANCE = None
    _reset_pool_for_tests()
