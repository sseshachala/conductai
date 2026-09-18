"""R13 (reviewer P2) — preserve reservation history when an agent is deleted.

Migration 0141 (Fix 5, #2107) set both agent_identity_id FKs to
``ON DELETE CASCADE`` so that deleting an agent also cleaned up its
budget row. That was correct for ``guard_spend_budgets`` (config —
deleting an agent means its budget config goes away), but WRONG for
``budget_reservations`` (durable accounting history — deleting an
agent erases the record of what they spent). Reviewer R13 flagged
this: "separate deletable budget configuration from durable
accounting history."

Fix:

1. Change ``budget_reservations.agent_identity_id`` FK from CASCADE
   back to SET NULL. Deleting the agent now nulls the column on the
   reservation row but the row itself survives.
2. Add ``deleted_agent_identity_id TEXT`` column that can hold the
   original agent id string as a tombstone. Populated by a future
   BEFORE DELETE trigger or app-level cleanup (not wired here — this
   migration is schema-only).
3. Keep ``guard_spend_budgets.agent_identity_id`` on CASCADE — budget
   config is not history and admins expect it to disappear with the
   agent.

Backward compat: SET NULL is the same behavior migration 0140 had
originally (before 0141 flipped it to CASCADE). Existing rows are
untouched.
"""
from alembic import op
import sqlalchemy as sa


revision = "0143"
down_revision = "0142"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Flip the reservation FK back to SET NULL so durable history survives.
    op.drop_constraint(
        "fk_budget_reservations_agent_identity",
        "budget_reservations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_budget_reservations_agent_identity",
        source_table="budget_reservations",
        referent_table="agent_identities",
        local_cols=["agent_identity_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )

    # Tombstone column: nullable String(36) that a future trigger or app-
    # level delete path can populate with the agent's original id before
    # the FK nulls the primary agent_identity_id column. Nullable so
    # existing rows and the immediate-post-delete state are both valid.
    op.add_column(
        "budget_reservations",
        sa.Column("deleted_agent_identity_id", sa.String(36), nullable=True),
    )
    op.create_index(
        "ix_budget_reservations_deleted_agent",
        "budget_reservations",
        ["workspace_id", "deleted_agent_identity_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_budget_reservations_deleted_agent",
        table_name="budget_reservations",
    )
    op.drop_column("budget_reservations", "deleted_agent_identity_id")

    op.drop_constraint(
        "fk_budget_reservations_agent_identity",
        "budget_reservations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_budget_reservations_agent_identity",
        source_table="budget_reservations",
        referent_table="agent_identities",
        local_cols=["agent_identity_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )
