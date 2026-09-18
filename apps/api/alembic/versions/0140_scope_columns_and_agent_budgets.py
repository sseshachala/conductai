"""Add agent_identity scope to guard_spend_budgets + scope columns to budget_reservations.

Enables agent-scoped budget rows (per Agent Identity, not just per Clerk user
or per ai_tool) and lets the ledger record which scope each reservation was
made under. That coverage is what the all-permit reservation contract in the
follow-up ledger-wiring PR requires: for a given request scoped to
``(workspace, agent, transport, client_tool)`` the ledger must be able to
reserve against every applicable budget row, and every reservation row must
carry the scope keys back to the audit chain via ``request_id``.

All new columns are nullable so existing rows, existing writers, and the
existing ``BudgetLedger`` primitive keep working unchanged. The lookup
precedence walk + ``reserve_all()`` semantics land in a later PR that
consumes these columns.

Schema additions:

- ``guard_spend_budgets.agent_identity_id`` — nullable String(36) FK to
  ``agent_identities.id``, ondelete=SET NULL (budget rows survive identity
  deletion but decay to workspace-scoped meaning).
- ``budget_reservations.agent_identity_id`` — same shape, same rationale.
- ``budget_reservations.source`` — nullable Text. Server-stamped transport
  (``'gateway'`` | ``'mcp'`` | ``'workflow'``). Matches the value written to
  ``guard_audit_events.source``. Nullable for the ledger primitive's existing
  single-scope callers.
- ``budget_reservations.client_tool`` — nullable Text. Client-declared tool
  string (``'claude-code'``, ``'cursor'``, ``'unknown'``). Optional even when
  ``source`` is set — the transport by itself is a valid scope.
- ``budget_reservations.request_id`` — nullable UUID. Correlates the
  reservation back to the audit chain via
  ``guard_audit_events.request_id`` (Phase 1 durable-audit column, added in
  migration 0132). Enables the drawer surface in PR-B to answer "for this
  audit row, what did we reserve?" in one lookup.

Indexes:

- ``ix_guard_spend_budgets_ws_agent`` — supports the lookup precedence
  walk when an agent-scoped budget exists for a request.
- ``ix_budget_reservations_scope`` — supports the reconciler's cold-start
  replay ("all open reservations for this workspace + agent + period").
- ``ix_budget_reservations_request_id`` — supports the drawer's per-request
  reservation lookup and any future request-scoped reconciliation.

Uniqueness update (drops + rewrites):

- Both partial-unique indexes on ``guard_spend_budgets`` (from migration
  0129) currently key on ``(workspace_id, [clerk_user_id,] ai_tool)``.
  Extending scope with agent_identity_id means the same
  ``(workspace_id, clerk_user_id, ai_tool)`` triple must now be uniquely
  identified with agent_identity_id too — else two agent-scoped budgets
  differing only by agent would collide as duplicates on the workspace-
  default index. Both indexes are rewritten to include
  ``COALESCE(agent_identity_id, '')`` in the key tuple.
- Existing rows (agent_identity_id NULL) fill the empty slot and remain
  uniquely identified; no data loss.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0140"
down_revision = "0139"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── guard_spend_budgets: agent scope ─────────────────────────────
    op.add_column(
        "guard_spend_budgets",
        sa.Column("agent_identity_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_guard_spend_budgets_agent_identity",
        source_table="guard_spend_budgets",
        referent_table="agent_identities",
        local_cols=["agent_identity_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_guard_spend_budgets_ws_agent",
        "guard_spend_budgets",
        ["workspace_id", "agent_identity_id"],
    )

    # ── extend uniqueness to include agent_identity_id ───────────────
    # Same shape as migration 0129 (raw SQL for partial + COALESCE).
    op.execute("DROP INDEX IF EXISTS uq_guard_spend_workspace_default")
    op.execute("DROP INDEX IF EXISTS uq_guard_spend_workspace_member")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_guard_spend_workspace_default
        ON guard_spend_budgets (
            workspace_id,
            COALESCE(agent_identity_id, ''),
            COALESCE(ai_tool, '')
        )
        WHERE clerk_user_id IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_guard_spend_workspace_member
        ON guard_spend_budgets (
            workspace_id,
            clerk_user_id,
            COALESCE(agent_identity_id, ''),
            COALESCE(ai_tool, '')
        )
        WHERE clerk_user_id IS NOT NULL
        """
    )

    # ── budget_reservations: multi-scope columns ─────────────────────
    op.add_column(
        "budget_reservations",
        sa.Column("agent_identity_id", sa.String(36), nullable=True),
    )
    op.add_column(
        "budget_reservations",
        sa.Column("source", sa.Text(), nullable=True),
    )
    op.add_column(
        "budget_reservations",
        sa.Column("client_tool", sa.Text(), nullable=True),
    )
    op.add_column(
        "budget_reservations",
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_budget_reservations_agent_identity",
        source_table="budget_reservations",
        referent_table="agent_identities",
        local_cols=["agent_identity_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_budget_reservations_scope",
        "budget_reservations",
        ["workspace_id", "agent_identity_id", "period_key"],
    )
    op.create_index(
        "ix_budget_reservations_request_id",
        "budget_reservations",
        ["request_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_budget_reservations_request_id", table_name="budget_reservations")
    op.drop_index("ix_budget_reservations_scope", table_name="budget_reservations")
    op.drop_constraint(
        "fk_budget_reservations_agent_identity",
        "budget_reservations",
        type_="foreignkey",
    )
    op.drop_column("budget_reservations", "request_id")
    op.drop_column("budget_reservations", "client_tool")
    op.drop_column("budget_reservations", "source")
    op.drop_column("budget_reservations", "agent_identity_id")

    # Restore the pre-0140 uniqueness shape (no agent_identity_id in key).
    op.execute("DROP INDEX IF EXISTS uq_guard_spend_workspace_default")
    op.execute("DROP INDEX IF EXISTS uq_guard_spend_workspace_member")
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_guard_spend_workspace_default
        ON guard_spend_budgets (workspace_id, COALESCE(ai_tool, ''))
        WHERE clerk_user_id IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_guard_spend_workspace_member
        ON guard_spend_budgets (workspace_id, clerk_user_id, COALESCE(ai_tool, ''))
        WHERE clerk_user_id IS NOT NULL
        """
    )

    op.drop_index("ix_guard_spend_budgets_ws_agent", table_name="guard_spend_budgets")
    op.drop_constraint(
        "fk_guard_spend_budgets_agent_identity",
        "guard_spend_budgets",
        type_="foreignkey",
    )
    op.drop_column("guard_spend_budgets", "agent_identity_id")
