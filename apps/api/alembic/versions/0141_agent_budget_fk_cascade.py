"""Fix 5 (P2 reviewer callout) — CASCADE agent deletion into scoped budgets.

Reviewer P2: ``ON DELETE SET NULL`` on ``guard_spend_budgets.agent_identity_id``
and ``budget_reservations.agent_identity_id`` (introduced by migration 0140)
turns an agent-deleted row into a workspace-wide row, because NULL in the
scope tuple means "any agent." Two failure modes:

1. Silent scope escalation. Deleting agent X converts a per-agent budget
   into a workspace-wide budget with the same monthly limit. Nobody
   configured that.
2. Unique-index collision. If a workspace-default row already exists,
   the SET NULL cannot land -- the partial unique index rejects it, and
   the agent deletion transaction rolls back. The admin sees an
   opaque FK error.

Fix: replace SET NULL with CASCADE on both FKs. Deleting an agent now
also deletes budget rows + open reservations scoped to that agent. Two
consequences by design:

- No orphaned rows silently escalate.
- Open reservations for a deleted agent disappear from the durable log
  too. The reconciler will not re-inflate a counter for a scope whose
  agent no longer exists (which is correct: nothing can spend against
  that scope anymore either).

Alternative considered: ondelete=RESTRICT so the admin must delete the
budget row first. Rejected because CASCADE is more consistent with how
the workspace FK behaves (workspaces already CASCADE into budgets and
reservations).
"""
from alembic import op


revision = "0141"
down_revision = "0140"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── guard_spend_budgets.agent_identity_id: SET NULL -> CASCADE ──
    op.drop_constraint(
        "fk_guard_spend_budgets_agent_identity",
        "guard_spend_budgets",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_guard_spend_budgets_agent_identity",
        source_table="guard_spend_budgets",
        referent_table="agent_identities",
        local_cols=["agent_identity_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # ── budget_reservations.agent_identity_id: SET NULL -> CASCADE ──
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


def downgrade() -> None:
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

    op.drop_constraint(
        "fk_guard_spend_budgets_agent_identity",
        "guard_spend_budgets",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_guard_spend_budgets_agent_identity",
        source_table="guard_spend_budgets",
        referent_table="agent_identities",
        local_cols=["agent_identity_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )
