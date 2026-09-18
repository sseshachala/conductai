"""R1 (reviewer P1) — persist clerk_user_id on budget_reservations.

The Fix 1 (P1 #1) refactor of the ledger's Redis key layout added
``clerk_user_id`` to the scope tuple used by every reserve/release/
commit/reconcile call, but the durable-log column was never added.
That caused two runtime AttributeError crashes reviewer reproduced:

- ``BudgetLedger.reconcile()`` reading ``BudgetReservation.clerk_user_id``.
- PR #2109 ``list_reservations_for_request`` endpoint serializing an
  ORM row that has no such attribute.

This migration adds the column and an index for the reconciler's
scope-exact filter. Nullable so pre-0142 rows stay valid; null means
"workspace-wide", matching the pre-Fix-1 key shape.
"""
from alembic import op
import sqlalchemy as sa


revision = "0142"
down_revision = "0141"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "budget_reservations",
        sa.Column("clerk_user_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_budget_reservations_scope_user",
        "budget_reservations",
        ["workspace_id", "clerk_user_id", "period_key"],
    )


def downgrade() -> None:
    op.drop_index("ix_budget_reservations_scope_user", table_name="budget_reservations")
    op.drop_column("budget_reservations", "clerk_user_id")
