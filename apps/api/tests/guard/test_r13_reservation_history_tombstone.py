"""R13 (reviewer P2) — reservation history survives agent deletion.

Migration 0141 set both agent_identity_id FKs to CASCADE. Correct for
``guard_spend_budgets`` (config), wrong for ``budget_reservations``
(history). Deleting an agent erased the record of what they spent.

Post-fix (migration 0143):

- ``budget_reservations.agent_identity_id`` FK is ``SET NULL`` so the
  history row survives with a null agent (meaning "we recorded this
  reservation for a since-deleted agent").
- ``deleted_agent_identity_id`` tombstone column captures the original
  id for drawer / history rendering.
- ``guard_spend_budgets.agent_identity_id`` remains CASCADE (config
  disappears with the agent, as admins expect).

Structural tests — the actual runtime DELETE + query behavior requires
a live Postgres and lives in the epic's chaos suite.
"""
from __future__ import annotations


def test_budget_reservations_has_tombstone_column():
    from app.modules.guard.models import BudgetReservation

    cols = set(BudgetReservation.__table__.columns.keys())
    assert "deleted_agent_identity_id" in cols, (
        "R13 tombstone column missing — deleting an agent will leave "
        "reservation history without any way to render its origin."
    )


def test_reservation_agent_fk_is_set_null_not_cascade():
    from app.modules.guard.models import BudgetReservation

    fk = None
    for c in BudgetReservation.__table__.columns:
        if c.name != "agent_identity_id":
            continue
        for foreign_key in c.foreign_keys:
            fk = foreign_key
            break
    assert fk is not None, "agent_identity_id FK missing on budget_reservations"
    assert fk.ondelete == "SET NULL", (
        f"R13 regressed: reservation FK ondelete is {fk.ondelete!r}, "
        "expected 'SET NULL'. Agent deletion would erase history."
    )


def test_budget_row_agent_fk_still_cascades():
    """Guard against an over-correction — the budget CONFIG row still
    disappears with the agent. Only history is preserved."""
    from app.modules.guard.models import GuardSpendBudget

    fk = None
    for c in GuardSpendBudget.__table__.columns:
        if c.name != "agent_identity_id":
            continue
        for foreign_key in c.foreign_keys:
            fk = foreign_key
            break
    assert fk is not None
    assert fk.ondelete == "CASCADE", (
        f"guard_spend_budgets FK regressed to {fk.ondelete!r}. R13 "
        "only changes the reservation history FK, not budget config."
    )


def test_tombstone_index_exists():
    """Historical lookup by tombstoned agent needs an index."""
    from app.modules.guard.models import BudgetReservation

    names = {i.name for i in BudgetReservation.__table__.indexes}
    assert "ix_budget_reservations_deleted_agent" in names, (
        "R13 tombstone index missing — historical lookup by original "
        "agent id will full-scan."
    )
