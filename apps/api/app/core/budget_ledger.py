"""PR 6d — atomic budget-reservation ledger.

Closes the race window in the existing spend-cap enforcement path where
two concurrent requests each read ``monthly_cost < cap`` and both
proceed, together spending past the cap.

State model (all state is Redis-authoritative; Postgres is the durable
recovery log):

- **committed** — spend already recorded for the current period. Redis
  counter ``budget:{ws}:{tool}:{period}:committed``. Seeded from
  ``guard_audit_events`` on cold start by ``reconcile_committed``.
  ``commit(reservation, actual)`` INCRBYs it.
- **reserved** — aggregate in-flight reservation. Redis counter
  ``budget:{ws}:{tool}:{period}:reserved``. Sum of all live
  reservation amounts.
- **reservations hash** — Redis HSET ``budget:{ws}:{tool}:{period}:res``
  keyed by reservation_id → estimated_cents. Provides *reservation
  identity*: release and commit can only affect a reservation that is
  still live. A second release for the same id is a no-op, so double-
  release cannot refund another request's slot (reviewer P1 #1).
- **budget_reservations** table — durable acceptance log. Every
  ``reserve`` writes a row *before* touching Redis; every ``release``
  / ``commit`` marks it resolved. On Redis cold start
  ``reconcile_reservations`` rebuilds the reserved counter + hash from
  open rows so a flush cannot silently restore capacity (reviewer P1
  #3).

Cap enforcement: ``committed + reserved + estimated <= cap``. All
three terms are read inside the same Lua script, so no caller-supplied
snapshot can become stale between check and increment (reviewer P1 #2).

Kill switch: ``BUDGET_LEDGER_ENABLED=false`` (default). No integration
into ``SpendCapPolicySource`` in this PR — primitive only.

Failure modes:
- Redis unreachable → ``BudgetDecision.REDIS_DOWN``. Callers should
  fall through to the existing DB-based ``budget_check`` path.
  ``BUDGET_LEDGER_FAIL_CLOSED=true`` overrides to strict refuse.
- Cold worker before reconciler → ``BudgetDecision.NOT_READY``.
  Callers should treat as fail-closed (or fall through, at ops's
  discretion). Once ``reconcile_all`` has run, the counter matches
  the durable log.
"""
from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

import redis as _redis_sync
import structlog
from sqlalchemy import func
from sqlalchemy.orm import Session

log = structlog.get_logger()


def enabled() -> bool:
    return os.environ.get("BUDGET_LEDGER_ENABLED", "false").lower() in (
        "1", "true", "yes",
    )


def fail_closed() -> bool:
    return os.environ.get("BUDGET_LEDGER_FAIL_CLOSED", "false").lower() in (
        "1", "true", "yes",
    )


class BudgetDecision(Enum):
    ACCEPTED = "accepted"
    EXCEEDED = "exceeded"
    REDIS_DOWN = "redis_down"
    NOT_READY = "not_ready"
    DISABLED = "disabled"


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    workspace_id: str
    ai_tool: str
    estimated_cents: int
    period_key: str
    # Fix 1 (P1 #1): scope fields so release/commit can reconstruct the
    # exact Redis key reserve() wrote against. Without these two, two
    # budgets differing only by clerk_user_id or agent_identity_id
    # shared one counter and produced 100c-request/200c-committed.
    clerk_user_id: str | None = None
    agent_identity_id: str | None = None


# ── Redis client (sync, shared pool) ────────────────────────────────

_pool: _redis_sync.ConnectionPool | None = None


def _redis_url() -> str:
    return os.environ.get("REDIS_URL", "redis://localhost:6379")


def _r() -> _redis_sync.Redis:
    global _pool
    if _pool is None:
        _pool = _redis_sync.ConnectionPool.from_url(
            _redis_url(), decode_responses=True,
        )
    return _redis_sync.Redis(connection_pool=_pool)


def _reset_pool_for_tests() -> None:
    global _pool
    _pool = None


# ── Period helpers ──────────────────────────────────────────────────

def monthly_period_key(now: datetime | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    return f"{now.year:04d}-{now.month:02d}"


def _period_start(period_key: str) -> datetime:
    year, month = period_key.split("-")
    return datetime(int(year), int(month), 1, tzinfo=timezone.utc)


def _seconds_until_next_period(now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    if now.month == 12:
        end = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        end = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
    return int((end - now).total_seconds()) + 3600  # 1h slack


def _scope_slug(user: str | None, agent: str | None, tool: str | None) -> str:
    """Canonical Redis key segment for a budget scope tuple.

    Fix 1 (P1 #1): keys must distinguish
    (user=None, agent=None, tool=None) from (user=None, agent=X, tool=None)
    from (user=Y, agent=None, tool=None). Uses '_' as the None sigil so
    distinct scope tuples never collide on the same Redis counter.
    """
    return f"{user or '_'}:{agent or '_'}:{tool or '_all'}"


def _reserved_key(ws, user, agent, tool, period):
    return f"budget:{ws}:{_scope_slug(user, agent, tool)}:{period}:reserved"


def _committed_key(ws, user, agent, tool, period):
    return f"budget:{ws}:{_scope_slug(user, agent, tool)}:{period}:committed"


def _res_hash_key(ws, user, agent, tool, period):
    return f"budget:{ws}:{_scope_slug(user, agent, tool)}:{period}:res"


# R11 fix (reviewer P1): known server-stamped transport identifiers. A
# budget row keyed on one of these caps aggregate spend routed through
# that surface regardless of client_tool. The reconciler must filter
# audit events by ``source == transport`` (not ai_tool) so cursor +
# claude-code + all other client tools flowing through the gateway
# count against the gateway cap.
#
# Source of truth: config/transports.json. Hardcoded here to avoid an
# import cycle on ledger init.
_TRANSPORT_IDS = frozenset({"gateway", "mcp", "workflow", "runtime"})


def _is_transport(ai_tool: str | None) -> bool:
    """True when ai_tool names a server-stamped transport surface."""
    return ai_tool in _TRANSPORT_IDS


def _ready_key(ws, user, agent, tool, period):
    """Set after reconciler completes; presence means the counters
    reflect the durable log."""
    return f"budget:{ws}:{_scope_slug(user, agent, tool)}:{period}:ready"


# ── Lua scripts ──────────────────────────────────────────────────────
#
# Every mutating operation runs inside Lua so the check → mutation
# sequence cannot interleave with a concurrent operation. Redis
# scripting is single-threaded per node.

# KEYS: reserved, committed, res_hash, ready
# ARGV: reservation_id, estimated, cap, ttl
_RESERVE_SCRIPT = """
if redis.call('EXISTS', KEYS[4]) == 0 then
    return {-1, 0, 0}
end
local reservation_id = ARGV[1]
local estimated = tonumber(ARGV[2])
local cap = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

local reserved = tonumber(redis.call('GET', KEYS[1]) or '0')
local committed = tonumber(redis.call('GET', KEYS[2]) or '0')

if reserved + committed + estimated > cap then
    return {0, reserved, committed}
end

redis.call('HSET', KEYS[3], reservation_id, estimated)
redis.call('EXPIRE', KEYS[3], ttl)
local new_reserved = redis.call('INCRBY', KEYS[1], estimated)
redis.call('EXPIRE', KEYS[1], ttl)
redis.call('EXPIRE', KEYS[2], ttl)
return {1, new_reserved, committed}
"""


# KEYS: reserved, res_hash
# ARGV: reservation_id, ttl
_RELEASE_SCRIPT = """
local reservation_id = ARGV[1]
local ttl = tonumber(ARGV[2])

local amount = tonumber(redis.call('HGET', KEYS[2], reservation_id) or '0')
if amount == 0 then
    return 0
end
redis.call('HDEL', KEYS[2], reservation_id)
local new_val = redis.call('DECRBY', KEYS[1], amount)
if new_val <= 0 then
    redis.call('DEL', KEYS[1])
else
    -- Preserve the counter's TTL — a partial refund must not turn a
    -- period-scoped counter into a leaked-forever key.
    redis.call('EXPIRE', KEYS[1], ttl)
end
return amount
"""


# KEYS: reserved, committed, res_hash
# ARGV: reservation_id, actual, ttl
_COMMIT_SCRIPT = """
local reservation_id = ARGV[1]
local actual = tonumber(ARGV[2])
local ttl = tonumber(ARGV[3])

local estimated = tonumber(redis.call('HGET', KEYS[3], reservation_id) or '0')
if estimated == 0 then
    return 0
end
redis.call('HDEL', KEYS[3], reservation_id)
local new_reserved = redis.call('DECRBY', KEYS[1], estimated)
if new_reserved <= 0 then
    redis.call('DEL', KEYS[1])
else
    redis.call('EXPIRE', KEYS[1], ttl)
end
redis.call('INCRBY', KEYS[2], actual)
redis.call('EXPIRE', KEYS[2], ttl)
return 1
"""


class BudgetLedger:
    """Sync-friendly reservation ledger with reservation identity,
    settlement, and cold-start recovery.
    """

    def __init__(self, *, redis_client: _redis_sync.Redis | None = None) -> None:
        self._redis = redis_client
        self._reservations_accepted = 0
        self._reservations_exceeded = 0
        self._reservations_redis_down = 0
        self._reservations_not_ready = 0
        self._releases = 0
        self._commits = 0

    def _client(self) -> _redis_sync.Redis:
        return self._redis if self._redis is not None else _r()

    # ── Reserve ─────────────────────────────────────────────────────
    def reserve(
        self,
        *,
        db: Session,
        workspace_id: str,
        ai_tool: str | None,
        estimated_cents: int,
        cap_cents: int,
        # PR-A1 scope columns + Fix 1 (P1 #1) clerk_user_id. Every scope
        # field is nullable; None resolves to the workspace-wide key
        # shape so legacy callers see zero behavior change.
        clerk_user_id: str | None = None,
        agent_identity_id: str | None = None,
        source: str | None = None,
        client_tool: str | None = None,
        request_id: str | None = None,
    ) -> tuple[BudgetDecision, Optional[Reservation]]:
        """Atomically reserve capacity.

        Writes a durable ``budget_reservations`` row *before* touching
        Redis. If Redis then refuses (or is down) the row is deleted so
        the durable log never contains phantom entries; if the worker
        crashes between the two, the row survives with status='open'
        and the reconciler will re-inflate Redis on next cold start.
        """
        if estimated_cents <= 0:
            return BudgetDecision.ACCEPTED, Reservation(
                reservation_id=uuid.uuid4().hex,
                workspace_id=workspace_id,
                ai_tool=ai_tool or "_all",
                estimated_cents=0,
                period_key=monthly_period_key(),
                clerk_user_id=clerk_user_id,
                agent_identity_id=agent_identity_id,
            )

        period = monthly_period_key()
        rid = uuid.uuid4().hex

        # 1) Durable row FIRST — this is the crash-safe log.
        from app.modules.guard.models import BudgetReservation
        row = BudgetReservation(
            id=uuid.UUID(rid),
            workspace_id=uuid.UUID(workspace_id) if _looks_like_uuid(workspace_id) else workspace_id,
            ai_tool=ai_tool,
            period_key=period,
            estimated_cents=estimated_cents,
            status="open",
            # R1 fix (reviewer P1) — persist clerk_user_id so reconcile
            # and the drawer can filter by the same scope tuple reserve
            # used for the Redis key. Column added by migration 0142.
            clerk_user_id=clerk_user_id,
            # PR-A1: scope columns — nullable, populated when the caller
            # supplies them. Correlate reservations to the audit chain.
            agent_identity_id=agent_identity_id,
            source=source,
            client_tool=client_tool,
            request_id=uuid.UUID(request_id) if request_id and _looks_like_uuid(request_id) else None,
        )
        # Fix 9 (P2 #9): commit the durable row NOW so it survives any
        # subsequent rollback of the caller's outer transaction. Any
        # Redis reserved-counter increment MUST have a matching
        # committed durable row so the reconciler's rebuild is
        # complete.
        try:
            db.add(row)
            db.commit()
        except Exception as e:  # noqa: BLE001
            db.rollback()
            log.warning("budget_ledger.reserve_db_failed", err=str(e))
            self._reservations_redis_down += 1
            return BudgetDecision.REDIS_DOWN, None

        # 2) Atomic Redis reserve.
        # Fix 1 (P1 #1): key by full scope so budgets differing only by
        # clerk_user_id or agent_identity_id do NOT share one counter.
        try:
            ret = self._client().eval(
                _RESERVE_SCRIPT, 4,
                _reserved_key(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period),
                _committed_key(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period),
                _res_hash_key(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period),
                _ready_key(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period),
                rid, estimated_cents, cap_cents,
                _seconds_until_next_period(),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("budget_ledger.reserve_redis_failed", err=str(e))
            self._reservations_redis_down += 1
            # R8 fix (reviewer P1): DO NOT delete the durable row. A
            # Redis exception is ambiguous — the connection may have
            # timed out AFTER Lua executed and Redis holds the
            # reservation. Deleting the row then would leak capacity
            # (Redis has 100c reserved with zero durable evidence).
            # Preserve the row as 'open'; the reconciler will either
            # confirm-and-mirror or classify-and-release when it runs.
            return BudgetDecision.REDIS_DOWN, None

        status = int(ret[0])
        if status == -1:
            # Reconciler has not run for this (ws, tool, period). Do
            # not accept blind — the reserved counter may be missing
            # entries from earlier crashed workers.
            self._reservations_not_ready += 1
            db.delete(row)
            db.commit()  # Fix 9 (P2 #9): durably remove phantom row
            return BudgetDecision.NOT_READY, None

        if status == 0:
            self._reservations_exceeded += 1
            db.delete(row)
            db.commit()  # Fix 9 (P2 #9)
            return BudgetDecision.EXCEEDED, None

        self._reservations_accepted += 1
        return BudgetDecision.ACCEPTED, Reservation(
            reservation_id=rid,
            workspace_id=workspace_id,
            ai_tool=ai_tool or "_all",
            estimated_cents=estimated_cents,
            period_key=period,
            clerk_user_id=clerk_user_id,
            agent_identity_id=agent_identity_id,
        )

    # ── Release ─────────────────────────────────────────────────────
    def release(self, db: Session, reservation: Reservation) -> None:
        """Refund the reservation. Idempotent by reservation_id — a
        second call finds the hash empty and no-ops. Cannot refund
        another reservation's capacity (reviewer P1 #1)."""
        if reservation.estimated_cents <= 0:
            return
        ai_tool = None if reservation.ai_tool == "_all" else reservation.ai_tool
        try:
            self._client().eval(
                _RELEASE_SCRIPT, 2,
                _reserved_key(
                    reservation.workspace_id,
                    reservation.clerk_user_id,
                    reservation.agent_identity_id,
                    ai_tool,
                    reservation.period_key,
                ),
                _res_hash_key(
                    reservation.workspace_id,
                    reservation.clerk_user_id,
                    reservation.agent_identity_id,
                    ai_tool,
                    reservation.period_key,
                ),
                reservation.reservation_id,
                _seconds_until_next_period(),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("budget_ledger.release_failed", err=str(e))
            # Fall through — DB row update still worth attempting so
            # the reconciler doesn't re-inflate a stale reservation.

        try:
            from app.modules.guard.models import BudgetReservation
            row = db.get(BudgetReservation, uuid.UUID(reservation.reservation_id))
            if row is not None and row.status == "open":
                row.status = "released"
                row.resolved_at = datetime.now(timezone.utc)
                # Fix 9 (P2 #9): commit the status flip so the
                # reconciler never re-inflates a released reservation.
                db.commit()
                self._releases += 1
        except Exception as e:  # noqa: BLE001
            db.rollback()
            log.warning("budget_ledger.release_db_failed", err=str(e))

    # ── Commit ──────────────────────────────────────────────────────
    def commit(
        self, db: Session, reservation: Reservation, actual_cents: int,
    ) -> None:
        """Convert reservation to committed spend. Refunds reserved
        by the estimated amount, adds actual_cents to committed.

        Idempotent by reservation_id — a second call finds the hash
        empty and no-ops."""
        if reservation.estimated_cents <= 0 and actual_cents <= 0:
            return
        ai_tool = None if reservation.ai_tool == "_all" else reservation.ai_tool
        try:
            self._client().eval(
                _COMMIT_SCRIPT, 3,
                _reserved_key(
                    reservation.workspace_id,
                    reservation.clerk_user_id,
                    reservation.agent_identity_id,
                    ai_tool,
                    reservation.period_key,
                ),
                _committed_key(
                    reservation.workspace_id,
                    reservation.clerk_user_id,
                    reservation.agent_identity_id,
                    ai_tool,
                    reservation.period_key,
                ),
                _res_hash_key(
                    reservation.workspace_id,
                    reservation.clerk_user_id,
                    reservation.agent_identity_id,
                    ai_tool,
                    reservation.period_key,
                ),
                reservation.reservation_id,
                max(0, actual_cents),
                _seconds_until_next_period(),
            )
        except Exception as e:  # noqa: BLE001
            log.warning("budget_ledger.commit_failed", err=str(e))

        try:
            from app.modules.guard.models import BudgetReservation
            row = db.get(BudgetReservation, uuid.UUID(reservation.reservation_id))
            if row is not None and row.status == "open":
                row.status = "committed"
                row.actual_cents = max(0, actual_cents)
                row.resolved_at = datetime.now(timezone.utc)
                # Fix 9 (P2 #9): commit the status flip so the
                # reconciler never re-inflates a committed reservation.
                db.commit()
                self._commits += 1
        except Exception as e:  # noqa: BLE001
            db.rollback()
            log.warning("budget_ledger.commit_db_failed", err=str(e))

    # ── Read-only ───────────────────────────────────────────────────
    def current_reserved_cents(
        self,
        workspace_id: str,
        ai_tool: str | None,
        *,
        clerk_user_id: str | None = None,
        agent_identity_id: str | None = None,
    ) -> int:
        period = monthly_period_key()
        try:
            return int(
                self._client().get(
                    _reserved_key(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period)
                )
                or 0
            )
        except Exception as e:  # noqa: BLE001
            log.warning("budget_ledger.read_reserved_failed", err=str(e))
            return 0

    def current_committed_cents(
        self,
        workspace_id: str,
        ai_tool: str | None,
        *,
        clerk_user_id: str | None = None,
        agent_identity_id: str | None = None,
    ) -> int:
        period = monthly_period_key()
        try:
            return int(
                self._client().get(
                    _committed_key(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period)
                )
                or 0
            )
        except Exception as e:  # noqa: BLE001
            log.warning("budget_ledger.read_committed_failed", err=str(e))
            return 0

    # ── Reconciler ──────────────────────────────────────────────────
    def reconcile(
        self,
        db: Session,
        workspace_id: str,
        ai_tool: str | None,
        *,
        clerk_user_id: str | None = None,
        agent_identity_id: str | None = None,
    ) -> None:
        """Rebuild the Redis state from the durable log for one
        (workspace, tool, period) key. MUST be called before any
        ``reserve()`` accepts requests for that key after a Redis
        flush or cold worker start.

        Order:
        1. Read committed from ``guard_audit_events`` for the current
           period → SET committed key
        2. Read open ``budget_reservations`` rows → SET reserved
           counter + populate res_hash
        3. SET ready flag

        Concurrent reconcile calls for the same key overwrite each
        other; the last one wins but they compute the same value from
        the same durable source, so this is safe."""
        period = monthly_period_key()
        period_start = _period_start(period)

        # 1) Committed from audit events.
        from app.modules.guard.models import GuardAuditEvent, BudgetReservation
        try:
            ws_uuid = uuid.UUID(workspace_id) if _looks_like_uuid(workspace_id) else workspace_id
        except (ValueError, AttributeError):
            ws_uuid = workspace_id

        q = db.query(
            func.coalesce(func.sum(GuardAuditEvent.cost_usd_after), 0.0)
        ).filter(
            GuardAuditEvent.workspace_id == ws_uuid,
            GuardAuditEvent.ts >= period_start,
        )
        if ai_tool is not None:
            # R11 fix (reviewer P1): a transport-scoped budget
            # (ai_tool in {'gateway','mcp',...}) must aggregate every
            # audit event routed through that surface regardless of
            # the caller's client_tool. Filter by ``source`` instead
            # of ``ai_tool`` for those rows. Non-transport (client
            # tool) budgets keep the ai_tool filter.
            if _is_transport(ai_tool):
                q = q.filter(GuardAuditEvent.source == ai_tool)
            else:
                q = q.filter(GuardAuditEvent.ai_tool == ai_tool)
        # Fix 1 (P1 #1): scope this budget's committed total by the same
        # null-or-matches predicate as per-request applicability. A
        # workspace-default budget (user=agent=tool=None) aggregates
        # every event; an agent-scoped budget aggregates only that
        # agent's spend.
        if clerk_user_id is not None:
            q = q.filter(GuardAuditEvent.clerk_user_id == clerk_user_id)
        if agent_identity_id is not None:
            q = q.filter(GuardAuditEvent.agent_identity_id == agent_identity_id)
        committed_usd = float(q.scalar() or 0.0)
        committed_cents = int(round(committed_usd * 100))

        # 2) Open reservations from durable log.
        open_rows = db.query(BudgetReservation).filter(
            BudgetReservation.workspace_id == ws_uuid,
            BudgetReservation.period_key == period,
            BudgetReservation.status == "open",
        )
        if ai_tool is None:
            open_rows = open_rows.filter(BudgetReservation.ai_tool.is_(None))
        else:
            open_rows = open_rows.filter(BudgetReservation.ai_tool == ai_tool)
        # Fix 1 (P1 #1): exact-scope match on reservation rows since
        # each budget owns only its own reservations under scope-aware
        # keying.
        if clerk_user_id is None:
            open_rows = open_rows.filter(BudgetReservation.clerk_user_id.is_(None))
        else:
            open_rows = open_rows.filter(BudgetReservation.clerk_user_id == clerk_user_id)
        if agent_identity_id is None:
            open_rows = open_rows.filter(BudgetReservation.agent_identity_id.is_(None))
        else:
            open_rows = open_rows.filter(BudgetReservation.agent_identity_id == agent_identity_id)

        reserved_total = 0
        hash_payload: dict[str, int] = {}
        for row in open_rows.all():
            hash_payload[str(row.id).replace("-", "")] = row.estimated_cents
            reserved_total += row.estimated_cents

        # 3) Write to Redis atomically.
        ttl = _seconds_until_next_period()
        client = self._client()
        pipe = client.pipeline()
        _res_key = _reserved_key(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period)
        _com_key = _committed_key(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period)
        _hash_key = _res_hash_key(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period)
        _rdy = _ready_key(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period)
        pipe.set(_com_key, committed_cents, ex=ttl)
        pipe.delete(_res_key)
        pipe.delete(_hash_key)
        if reserved_total > 0:
            pipe.set(_res_key, reserved_total, ex=ttl)
        if hash_payload:
            pipe.hset(_hash_key, mapping=hash_payload)
            pipe.expire(_hash_key, ttl)
        pipe.set(_rdy, "1", ex=ttl)
        pipe.execute()

    def stats(self) -> dict:
        return {
            "enabled": enabled(),
            "reservations_accepted": self._reservations_accepted,
            "reservations_exceeded": self._reservations_exceeded,
            "reservations_redis_down": self._reservations_redis_down,
            "reservations_not_ready": self._reservations_not_ready,
            "releases": self._releases,
            "commits": self._commits,
        }

    # ── Multi-scope helpers (PR-A1) ─────────────────────────────────
    #
    # The all-permit contract (per #2093 design review): each request may
    # apply to multiple budget rows (workspace + agent + transport +
    # client_tool). The gateway lifecycle wiring calls reserve_all() with
    # every applicable row from ``lookup_applicable_budgets()``; if ANY
    # underlying reserve() refuses, every previously accepted reservation
    # is released atomically and the caller sees a single decision.

    def reserve_all(
        self,
        *,
        db: Session,
        workspace_id: str,
        applicable_budgets: list,
        estimated_cents: int,
        agent_identity_id: str | None = None,
        source: str | None = None,
        client_tool: str | None = None,
        request_id: str | None = None,
    ) -> tuple[BudgetDecision, Optional[list[Reservation]], Optional[object]]:
        """All-or-nothing multi-scope reservation.

        For each budget row in ``applicable_budgets`` with
        ``hard_cap_enabled=True`` and a ``hard_limit_usd`` set, call
        ``reserve()`` with ``cap_cents = int(round(hard_limit_usd * 100))``.
        Budgets without hard enforcement are alerting-only — skipped.

        On any refusal, previously-accepted reservations are released via
        best-effort ``release()`` (idempotent). Returns
        ``(decision, accepted_or_None, refusing_budget_or_None)``:

        - ACCEPTED  -> ``(ACCEPTED, [Reservation, ...], None)``
        - refusal   -> ``(first_bad_decision, None, refusing_row)``
        - no budgets to reserve against -> ``(ACCEPTED, [], None)``

        The empty-list ACCEPTED case is important: it means "no hard cap
        applies here, dispatch is unconditionally allowed."
        """
        accepted: list[Reservation] = []
        for budget in applicable_budgets:
            if not getattr(budget, "hard_cap_enabled", False):
                continue
            hard_limit = getattr(budget, "hard_limit_usd", None)
            if hard_limit is None or hard_limit <= 0:
                continue
            cap_cents = int(round(float(hard_limit) * 100))

            decision, res = self.reserve(
                db=db,
                workspace_id=workspace_id,
                # Fix 1 (P1 #1): key the Redis counter by the BUDGET row's
                # own scope tuple, not the request scope. Each budget row
                # owns its own counter under scope-aware keying.
                ai_tool=budget.ai_tool,
                clerk_user_id=getattr(budget, "clerk_user_id", None),
                agent_identity_id=getattr(budget, "agent_identity_id", None),
                estimated_cents=estimated_cents,
                cap_cents=cap_cents,
                # Request-scope metadata for the durable audit correlation.
                source=source,
                client_tool=client_tool,
                request_id=request_id,
            )
            if decision != BudgetDecision.ACCEPTED:
                for r in accepted:
                    try:
                        self.release(db=db, reservation=r)
                    except Exception as e:  # noqa: BLE001
                        log.warning(
                            "budget_ledger.reserve_all_unwind_failed",
                            reservation_id=r.reservation_id,
                            err=str(e),
                        )
                return decision, None, budget
            accepted.append(res)
        return BudgetDecision.ACCEPTED, accepted, None

    def release_all(self, db: Session, reservations: list[Reservation]) -> None:
        """Release every reservation in the list. Idempotent + best-effort."""
        for r in reservations:
            try:
                self.release(db=db, reservation=r)
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "budget_ledger.release_all_failed",
                    reservation_id=r.reservation_id,
                    err=str(e),
                )

    def commit_all(
        self,
        db: Session,
        reservations: list[Reservation],
        actual_cents: int,
    ) -> None:
        """Commit every reservation with the SAME actual_cents.

        Each budget charged against the request receives the full
        ``actual_cents`` on its committed counter — not a proportional
        split. Individual failures are logged but do not stop iteration;
        the reconciler catches any orphaned open reservations later.
        """
        for r in reservations:
            try:
                self.commit(db=db, reservation=r, actual_cents=actual_cents)
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "budget_ledger.commit_all_failed",
                    reservation_id=r.reservation_id,
                    err=str(e),
                )


# ── Helpers ──────────────────────────────────────────────────────────

def _looks_like_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except (ValueError, AttributeError, TypeError):
        return False


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
