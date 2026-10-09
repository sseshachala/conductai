"""Budget ledger reserve / release / commit / read operations (mixin).

Extracted from ``budget_ledger.py`` (pure move, no behavior change);
``app.core.budget_ledger`` remains the public facade.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.core.budget_ledger_keys import (
    _committed_key,
    _looks_like_uuid,
    _reserved_key,
    _scope_keys,
    _seconds_until_next_period,
    monthly_period_key,
)
from app.core.budget_ledger_scripts import (
    _COMMIT_SCRIPT,
    _RELEASE_SCRIPT,
    _RESERVE_SCRIPT,
)
from app.core.budget_ledger_types import (
    _MICROS_PER_CENT,
    BudgetDecision,
    Reservation,
)

log = structlog.get_logger()


class _LedgerOpsMixin:
    # ── Reserve ─────────────────────────────────────────────────────
    def reserve(
        self,
        *,
        db: Session,
        workspace_id: str,
        ai_tool: str | None,
        estimated_cents: int | None = None,
        cap_cents: int | None = None,
        # R9 (reviewer P1): microdollar-precision alternatives. When
        # both a _cents and _micros kwarg are provided the micros value
        # wins — cents-mode callers stay backward-compatible until they
        # migrate.
        estimated_micros: int | None = None,
        cap_micros: int | None = None,
        # PR-A1 scope columns + Fix 1 (P1 #1) clerk_user_id.
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

        R9 unit contract: internally everything is micros. Cents-mode
        callers get scaled up by 10 000 at the boundary; the Redis
        counters and durable log speak micros.
        """
        if estimated_micros is None:
            estimated_micros = int(estimated_cents or 0) * _MICROS_PER_CENT
        if cap_micros is None:
            cap_micros = int(cap_cents or 0) * _MICROS_PER_CENT
        estimated_cents = max(1, estimated_micros // _MICROS_PER_CENT) if estimated_micros > 0 else 0
        cap_cents = cap_micros // _MICROS_PER_CENT
        if estimated_micros <= 0:
            return BudgetDecision.ACCEPTED, Reservation(
                reservation_id=uuid.uuid4().hex,
                workspace_id=workspace_id,
                ai_tool=ai_tool or "_all",
                estimated_cents=0,
                estimated_micros=0,
                period_key=monthly_period_key(),
                clerk_user_id=clerk_user_id,
                agent_identity_id=agent_identity_id,
            )

        period = monthly_period_key()
        rid = uuid.uuid4().hex

        # 0) Cold-start self-heal. The startup reconciler only enumerates
        # scopes that already have rows in guard_audit_events or
        # budget_reservations for the current period. A workspace's
        # FIRST-EVER reserve is invisible to it — :ready never gets set,
        # the Lua below returns -1, and every request 503s with NOT_READY
        # forever (fail-closed cold-start loop). Reconcile this specific
        # scope inline when :ready is missing so the Lua can proceed.
        # reconcile() is idempotent and empty-scope-safe (committed=0,
        # reserved=0, ready=1).
        _sk_precheck = _scope_keys(
            workspace_id, clerk_user_id, agent_identity_id, ai_tool, period
        )
        try:
            if not self._client().exists(_sk_precheck["ready"]):
                self.reconcile(
                    db=db,
                    workspace_id=workspace_id,
                    ai_tool=ai_tool,
                    clerk_user_id=clerk_user_id,
                    agent_identity_id=agent_identity_id,
                )
        except Exception as e:  # noqa: BLE001 — never let self-heal break the reserve
            log.warning("budget_ledger.reserve_ready_precheck_failed", err=str(e))

        # 1) Durable row FIRST — this is the crash-safe log.
        from app.modules.guard.models import BudgetReservation
        row = BudgetReservation(
            id=uuid.UUID(rid),
            workspace_id=uuid.UUID(workspace_id) if _looks_like_uuid(workspace_id) else workspace_id,
            ai_tool=ai_tool,
            period_key=period,
            estimated_cents=estimated_cents,
            # R9 (reviewer P1): microdollar precision on the durable log.
            estimated_micros=estimated_micros,
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

        # 2) Atomic Redis reserve. Fix 1 (P1 #1): key by full scope.
        _sk = _scope_keys(workspace_id, clerk_user_id, agent_identity_id, ai_tool, period)
        try:
            ret = self._client().eval(
                _RESERVE_SCRIPT, 4,
                _sk["reserved"], _sk["committed"], _sk["res_hash"], _sk["ready"],
                rid, estimated_micros, cap_micros,
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
            estimated_micros=estimated_micros,
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
        _sk = _scope_keys(
            reservation.workspace_id,
            reservation.clerk_user_id,
            reservation.agent_identity_id,
            ai_tool,
            reservation.period_key,
        )
        try:
            self._client().eval(
                _RELEASE_SCRIPT, 2,
                _sk["reserved"], _sk["res_hash"],
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
        self,
        db: Session,
        reservation: Reservation,
        actual_cents: int | None = None,
        *,
        actual_micros: int | None = None,
    ) -> None:
        """Convert reservation to committed spend. Refunds reserved
        by the estimated amount, adds actual_cents (or actual_micros)
        to committed.

        R9 (reviewer P1): actual_micros takes precedence when both are
        given. Callers that still pass actual_cents are supported via
        internal scaling — the Redis counter always sees micros.

        Idempotent by reservation_id — a second call finds the hash
        empty and no-ops."""
        # R9: normalize to micros internally.
        if actual_micros is None:
            actual_micros = int(actual_cents or 0) * _MICROS_PER_CENT
        # Backward-compat cent value for the DB row.
        actual_cents = actual_micros // _MICROS_PER_CENT if actual_micros > 0 else 0
        if reservation.estimated_cents <= 0 and actual_micros <= 0:
            return
        ai_tool = None if reservation.ai_tool == "_all" else reservation.ai_tool
        _sk = _scope_keys(
            reservation.workspace_id,
            reservation.clerk_user_id,
            reservation.agent_identity_id,
            ai_tool,
            reservation.period_key,
        )
        try:
            self._client().eval(
                _COMMIT_SCRIPT, 3,
                _sk["reserved"], _sk["committed"], _sk["res_hash"],
                reservation.reservation_id,
                max(0, actual_micros),
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
                row.actual_micros = max(0, actual_micros)
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
        return self.current_reserved_micros(
            workspace_id, ai_tool,
            clerk_user_id=clerk_user_id, agent_identity_id=agent_identity_id,
        ) // _MICROS_PER_CENT

    def current_reserved_micros(
        self,
        workspace_id: str,
        ai_tool: str | None,
        *,
        clerk_user_id: str | None = None,
        agent_identity_id: str | None = None,
    ) -> int:
        """R9: raw micros from the Redis reserved counter."""
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
        return self.current_committed_micros(
            workspace_id, ai_tool,
            clerk_user_id=clerk_user_id, agent_identity_id=agent_identity_id,
        ) // _MICROS_PER_CENT

    def current_committed_micros(
        self,
        workspace_id: str,
        ai_tool: str | None,
        *,
        clerk_user_id: str | None = None,
        agent_identity_id: str | None = None,
    ) -> int:
        """R9: raw micros from the Redis committed counter."""
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
