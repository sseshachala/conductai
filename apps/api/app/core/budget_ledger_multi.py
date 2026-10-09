"""Budget ledger all-or-nothing multi-scope helpers (mixin).

Extracted from ``budget_ledger.py`` (pure move, no behavior change);
``app.core.budget_ledger`` remains the public facade.
"""
from __future__ import annotations

from typing import Optional

import structlog
from sqlalchemy.orm import Session

from app.core.budget_ledger_types import (
    BudgetDecision,
    Reservation,
)

log = structlog.get_logger()


class _LedgerMultiScopeMixin:
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
        estimated_cents: int | None = None,
        estimated_micros: int | None = None,
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
            # R9: microdollar precision for cap comparison.
            cap_micros = int(round(float(hard_limit) * 1_000_000))
            cap_cents_scaled = cap_micros // 10_000

            decision, res = self.reserve(
                db=db,
                workspace_id=workspace_id,
                # Fix 1 (P1 #1): key the Redis counter by the BUDGET row's
                # own scope tuple, not the request scope.
                ai_tool=budget.ai_tool,
                clerk_user_id=getattr(budget, "clerk_user_id", None),
                agent_identity_id=getattr(budget, "agent_identity_id", None),
                estimated_cents=estimated_cents,
                estimated_micros=estimated_micros,
                cap_cents=cap_cents_scaled,
                cap_micros=cap_micros,
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
        actual_cents: int | None = None,
        *,
        actual_micros: int | None = None,
    ) -> None:
        """Commit every reservation with the SAME actual_cents (or actual_micros).

        Each budget charged against the request receives the full
        ``actual_cents`` on its committed counter — not a proportional
        split. Individual failures are logged but do not stop iteration;
        the reconciler catches any orphaned open reservations later.
        """
        for r in reservations:
            try:
                self.commit(
                    db=db,
                    reservation=r,
                    actual_cents=actual_cents,
                    actual_micros=actual_micros,
                )
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "budget_ledger.commit_all_failed",
                    reservation_id=r.reservation_id,
                    err=str(e),
                )
