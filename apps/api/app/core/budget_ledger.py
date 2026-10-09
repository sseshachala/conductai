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
import uuid  # noqa: F401  (re-exported for backward compatibility)

import redis as _redis_sync  # noqa: F401
import structlog

from app.core.budget_ledger_keys import (  # noqa: F401  (facade re-exports)
    _TRANSPORT_IDS,
    _committed_key,
    _is_transport,
    _looks_like_uuid,
    _period_start,
    _ready_key,
    _res_hash_key,
    _reserved_key,
    _scope_keys,
    _scope_slug,
    _seconds_until_next_period,
    monthly_period_key,
)
from app.core.budget_ledger_multi import _LedgerMultiScopeMixin
from app.core.budget_ledger_ops import _LedgerOpsMixin
from app.core.budget_ledger_reconcile import _LedgerReconcileMixin
from app.core.budget_ledger_redis import (  # noqa: F401  (facade re-exports)
    _REDIS_CONNECT_TIMEOUT_SEC,
    _REDIS_SOCKET_TIMEOUT_SEC,
    _r,
    _redis_url,
    _reset_pool_for_tests,
)
from app.core.budget_ledger_scripts import (  # noqa: F401  (facade re-exports)
    _COMMIT_SCRIPT,
    _RELEASE_SCRIPT,
    _RESERVE_SCRIPT,
)
from app.core.budget_ledger_types import (  # noqa: F401  (facade re-exports)
    _MICROS_PER_CENT,
    _MICROS_PER_USD,
    BudgetDecision,
    Reservation,
)

log = structlog.get_logger()


def enabled() -> bool:
    """Global kill switch. False = ledger is dark everywhere."""
    return os.environ.get("BUDGET_LEDGER_ENABLED", "false").lower() in (
        "1", "true", "yes",
    )


# Workspace-allowlist gate (canary rollout).
#
# Semantics:
#   BUDGET_LEDGER_ENABLED=false                              -> nothing enforces
#   BUDGET_LEDGER_ENABLED=true + ALLOWLIST unset / empty     -> all workspaces enforce (backward compat)
#   BUDGET_LEDGER_ENABLED=true + ALLOWLIST=*                 -> all workspaces enforce (explicit wildcard)
#   BUDGET_LEDGER_ENABLED=true + ALLOWLIST=ws1,ws2           -> only ws1, ws2 enforce
#
# ``enabled_for(workspace_id)`` is the correct check for any code
# path that has a workspace context. ``enabled()`` remains available
# for callers that predate the allowlist (they get global behavior).
_ALLOWLIST_ALL = "*"


def _allowlisted_workspaces() -> set[str] | None:
    """Return the parsed allowlist, or None to mean 'no restriction'.

    Unset OR empty OR '*' -> None (all workspaces).
    Comma-separated UUID list -> set of lowercase-normalized strings.
    """
    raw = os.environ.get("BUDGET_LEDGER_ALLOWLIST", "").strip()
    if not raw or raw == _ALLOWLIST_ALL:
        return None
    return {piece.strip().lower() for piece in raw.split(",") if piece.strip()}


def enabled_for(workspace_id: str | None) -> bool:
    """Combined kill switch + workspace allowlist.

    Any code path that has a workspace_id should call this instead of
    ``enabled()`` so the canary allowlist actually gates enforcement.
    """
    if not enabled():
        return False
    allowlist = _allowlisted_workspaces()
    if allowlist is None:
        # No restriction — every workspace enforces when the global
        # flag is on.
        return True
    if workspace_id is None:
        # A code path with no workspace context cannot be gated;
        # fail-closed to prevent accidental enforcement leakage.
        return False
    return str(workspace_id).lower() in allowlist


def fail_closed() -> bool:
    return os.environ.get("BUDGET_LEDGER_FAIL_CLOSED", "false").lower() in (
        "1", "true", "yes",
    )


class BudgetLedger(_LedgerOpsMixin, _LedgerReconcileMixin, _LedgerMultiScopeMixin):
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
