"""R2 (reviewer P1) — budget-ledger reconciler wiring + recovery worker.

The ledger primitive (``budget_ledger.py``) exposes a per-scope
``BudgetLedger.reconcile()`` that rebuilds the Redis counter for one
``(workspace, clerk_user_id, agent_identity_id, ai_tool, period)``
tuple from the durable log. It is a building block — nobody was
calling it in production. Consequences the reviewer surfaced:

- Fresh Redis or first-of-month cold start rejects capped requests
  indefinitely (the Lua script returns ``NOT_READY`` when the ``ready``
  key is absent).
- R8's preserved durable rows (``reserve()`` on Redis exception now
  keeps the row instead of deleting it) have no consumer.
- Month rollover breaks — new-period keys never get initialized.

This module wires the primitive into two real callers:

1. **Startup enumeration** (``run_startup_reconciliation``): on process
   start, enumerate every ``(workspace, scope)`` tuple that has an
   open reservation OR at least one committed audit event in the
   current period. Call ``reconcile()`` on each so Redis ``ready``
   keys are set before the first ``reserve()`` runs.

2. **Recovery worker** (``run_recovery_sweep``): a periodic sweep
   that classifies stale open reservations. A reservation whose
   lease has expired past the safety window is either
   ``committed`` (if the audit row lifecycle_state=finalized with
   a real cost) or ``released`` (if the audit row is orphaned or
   the reservation is a phantom from R8's Redis-exception path).

Both entry points are guarded by ``budget_ledger.enabled()`` so they
are no-ops when the ledger flag is off. Both are also idempotent — a
repeated startup run against a warm cache produces zero net changes,
and the recovery worker treats already-resolved rows as no-ops.

Metrics (Prometheus, see observability/metrics.py):

- ``guard_budget_reconcile_runs_total`` — counter, label ``outcome``
  (success | error).
- ``guard_budget_reconcile_scopes_reconciled_total`` — counter,
  incremented per scope reconciled at startup.
- ``guard_budget_recovery_sweep_actions_total`` — counter, label
  ``action`` (committed | released | left_open).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterable

import structlog

log = structlog.get_logger(__name__)


# Grace period after a reservation's lease expiry before the recovery
# worker considers it stale. Guards against a benign clock skew
# between the ledger writer and the sweep worker.
_RECOVERY_GRACE_SECONDS = 300


# ── Enumeration helpers ────────────────────────────────────────────


def _enumerate_open_reservation_scopes(db) -> Iterable[tuple[str, str | None, str | None, str | None]]:
    """Yield every distinct scope tuple with at least one open
    reservation in the current period.

    Returns tuples of ``(workspace_id_str, clerk_user_id,
    agent_identity_id, ai_tool)`` — the scope keys ``reconcile()``
    accepts. ``ai_tool`` is normalized from the sentinel ``'_all'`` back
    to ``None`` so it matches how the ledger keys Redis.
    """
    from app.core.budget_ledger import monthly_period_key
    from app.modules.guard.models import BudgetReservation

    period = monthly_period_key()
    rows = (
        db.query(
            BudgetReservation.workspace_id,
            BudgetReservation.clerk_user_id,
            BudgetReservation.agent_identity_id,
            BudgetReservation.ai_tool,
        )
        .filter(
            BudgetReservation.period_key == period,
            BudgetReservation.status == "open",
        )
        .distinct()
        .all()
    )
    for ws, user, agent, tool in rows:
        yield str(ws), user, agent, (None if tool == "_all" else tool)


def _enumerate_committed_scopes(db) -> Iterable[tuple[str, str | None, str | None, str | None]]:
    """Yield every distinct scope tuple with committed spend in the
    current period.

    Committed spend lives on ``guard_audit_events`` — the reconciler
    aggregates ``cost_usd_after`` for the period per scope. A scope
    that had traffic but no open reservation still needs its ``ready``
    key set so subsequent ``reserve()`` calls do not return NOT_READY.
    """
    from app.core.budget_ledger import _period_start, monthly_period_key
    from app.modules.guard.models import GuardAuditEvent

    period = monthly_period_key()
    period_start = _period_start(period)
    rows = (
        db.query(
            GuardAuditEvent.workspace_id,
            GuardAuditEvent.clerk_user_id,
            GuardAuditEvent.agent_identity_id,
            GuardAuditEvent.ai_tool,
        )
        .filter(GuardAuditEvent.ts >= period_start)
        .filter(GuardAuditEvent.cost_usd_after.isnot(None))
        .distinct()
        .all()
    )
    for ws, user, agent, tool in rows:
        yield str(ws), user, agent, tool


# ── Startup entry point ────────────────────────────────────────────


def run_startup_reconciliation(session_factory=None) -> dict:
    """Reconcile every scope with open reservations OR committed traffic
    in the current period.

    Called from ``main.py::_startup``. Idempotent — a second run
    against a warm cache is a no-op.

    Returns a dict with ``scopes_reconciled`` and ``errors`` counts so
    the caller can log a summary.
    """
    from app.core.budget_ledger import enabled as _ledger_enabled, get_budget_ledger

    if not _ledger_enabled():
        log.info("guard.budget.reconcile_startup_skipped_flag_off")
        return {"scopes_reconciled": 0, "errors": 0, "skipped": True}
    # Workspace-allowlist gate: even with the global flag on, only
    # reconcile scopes for workspaces that have opted in.
    from app.core.budget_ledger import _allowlisted_workspaces
    _allow = _allowlisted_workspaces()

    if session_factory is None:
        from app.core.database import SessionLocal
        session_factory = SessionLocal

    ledger = get_budget_ledger()
    scopes: set[tuple[str, str | None, str | None, str | None]] = set()
    reconciled = 0
    errors = 0

    db = session_factory()
    try:
        # Union both enumerations so we cover open reservations AND
        # committed-but-no-reservation scopes (e.g. legacy traffic
        # before the ledger was enabled).
        for s in _enumerate_open_reservation_scopes(db):
            scopes.add(s)
        for s in _enumerate_committed_scopes(db):
            scopes.add(s)
        if _allow is not None:
            scopes = {s for s in scopes if str(s[0]).lower() in _allow}
    except Exception as exc:  # noqa: BLE001
        log.exception("guard.budget.reconcile_startup_enumerate_failed", err=str(exc))
        errors += 1
        scopes = set()
    finally:
        db.close()

    for ws, user, agent, tool in scopes:
        db = session_factory()
        try:
            ledger.reconcile(
                db=db,
                workspace_id=ws,
                ai_tool=tool,
                clerk_user_id=user,
                agent_identity_id=agent,
            )
            reconciled += 1
            try:
                from app.modules.guard.observability.metrics import (
                    GUARD_BUDGET_RECONCILE_SCOPES,
                )
                GUARD_BUDGET_RECONCILE_SCOPES.inc()
            except Exception:  # noqa: BLE001
                pass
        except Exception as exc:  # noqa: BLE001
            errors += 1
            log.warning(
                "guard.budget.reconcile_scope_failed",
                err=str(exc),
                workspace_id=ws,
                ai_tool=tool,
            )
        finally:
            db.close()

    try:
        from app.modules.guard.observability.metrics import GUARD_BUDGET_RECONCILE_RUNS
        GUARD_BUDGET_RECONCILE_RUNS.labels(outcome="success" if errors == 0 else "partial").inc()
    except Exception:  # noqa: BLE001
        pass

    log.info(
        "guard.budget.reconcile_startup_complete",
        scopes_reconciled=reconciled,
        errors=errors,
    )
    return {"scopes_reconciled": reconciled, "errors": errors, "skipped": False}


# ── Recovery sweep ─────────────────────────────────────────────────


def _classify_stale_reservation(db, row) -> str:
    """Return the recovery action for a stale open reservation.

    Rules:

    - If the correlated audit row (via ``request_id``) is finalized
      with a real cost, the reservation should be ``committed``
      (settle now).
    - If the audit row is orphaned/expired/absent, the reservation
      is either a phantom (R8's Redis-exception path) or genuinely
      abandoned. Either way ``released`` is safe: released Redis
      capacity, and the reconciler rebuilds it from the durable log
      on next run if Redis had actually applied.
    - If neither condition holds cleanly (audit row still in
      ``accepted``), leave open — the audit's own lease-expiry sweep
      will resolve it eventually.
    """
    from app.modules.guard.models import GuardAuditEvent

    if row.request_id is None:
        return "released"

    ev = (
        db.query(GuardAuditEvent)
        .filter(GuardAuditEvent.request_id == row.request_id)
        .first()
    )
    if ev is None:
        return "released"
    if ev.lifecycle_state == "finalized" and ev.cost_usd_after is not None:
        return "committed"
    if ev.lifecycle_state in ("orphaned", "expired"):
        return "released"
    return "left_open"


def run_recovery_sweep(session_factory=None, *, stale_seconds: int | None = None) -> dict:
    """Sweep open reservations past the recovery-grace deadline.

    Returns a dict with counts per action. Idempotent — an already-
    resolved row is skipped. Metric-emitting.
    """
    from app.core.budget_ledger import (
        Reservation,
        enabled as _ledger_enabled,
        get_budget_ledger,
    )

    if not _ledger_enabled():
        return {
            "committed": 0,
            "released": 0,
            "left_open": 0,
            "errors": 0,
            "skipped": True,
        }
    # Recovery sweep only touches allowlisted workspaces so a non-
    # opted-in workspace never sees any ledger activity.
    from app.core.budget_ledger import _allowlisted_workspaces
    _allow_recovery = _allowlisted_workspaces()

    if session_factory is None:
        from app.core.database import SessionLocal
        session_factory = SessionLocal

    threshold = stale_seconds if stale_seconds is not None else _RECOVERY_GRACE_SECONDS
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=threshold)

    ledger = get_budget_ledger()
    actions = {"committed": 0, "released": 0, "left_open": 0, "errors": 0}

    from app.modules.guard.models import BudgetReservation

    db = session_factory()
    try:
        _q = db.query(BudgetReservation).filter(
            BudgetReservation.status == "open",
            BudgetReservation.created_at < cutoff,
        )
        if _allow_recovery is not None:
            _q = _q.filter(
                BudgetReservation.workspace_id.in_(_allow_recovery)
            )
        stale = _q.limit(500).all()
    except Exception as exc:  # noqa: BLE001
        log.exception("guard.budget.recovery_sweep_query_failed", err=str(exc))
        db.close()
        return {**actions, "errors": actions["errors"] + 1, "skipped": False}

    for row in stale:
        try:
            action = _classify_stale_reservation(db, row)
        except Exception as exc:  # noqa: BLE001
            log.warning("guard.budget.recovery_classify_failed", err=str(exc), row_id=str(row.id))
            actions["errors"] += 1
            continue

        if action == "left_open":
            actions["left_open"] += 1
            continue

        # Rehydrate a Reservation handle so we can call the ledger's
        # single-scope release()/commit() with the correct scope keys.
        res = Reservation(
            reservation_id=str(row.id),
            workspace_id=str(row.workspace_id),
            ai_tool=row.ai_tool or "_all",
            estimated_cents=int(row.estimated_cents),
            period_key=row.period_key,
            clerk_user_id=row.clerk_user_id,
            agent_identity_id=row.agent_identity_id,
        )

        try:
            if action == "committed":
                # Best-effort actual cost from the correlated audit row.
                from app.modules.guard.models import GuardAuditEvent
                ev = (
                    db.query(GuardAuditEvent)
                    .filter(GuardAuditEvent.request_id == row.request_id)
                    .first()
                )
                actual_usd = float(ev.cost_usd_after or 0.0) if ev else 0.0
                actual_cents = int(round(actual_usd * 100))
                ledger.commit(db=db, reservation=res, actual_cents=actual_cents)
            elif action == "released":
                ledger.release(db=db, reservation=res)
            actions[action] += 1
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "guard.budget.recovery_action_failed",
                err=str(exc),
                row_id=str(row.id),
                action=action,
            )
            actions["errors"] += 1

    db.close()

    try:
        from app.modules.guard.observability.metrics import GUARD_BUDGET_RECOVERY_ACTIONS
        for act in ("committed", "released", "left_open"):
            if actions[act] > 0:
                GUARD_BUDGET_RECOVERY_ACTIONS.labels(action=act).inc(actions[act])
    except Exception:  # noqa: BLE001
        pass

    log.info("guard.budget.recovery_sweep_complete", **actions)
    return {**actions, "skipped": False}


__all__ = [
    "run_startup_reconciliation",
    "run_recovery_sweep",
    "_RECOVERY_GRACE_SECONDS",
]
