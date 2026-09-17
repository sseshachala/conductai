"""Budget reservation durable log — PR 6d atomic ledger.

Backs the Redis reservation counter with a Postgres audit trail so a
Redis flush or mid-request worker crash cannot silently restore
spending capacity. The reconciler in ``app/core/budget_ledger.py``
reads open rows on cold start and rehydrates Redis before accepting
new reservations for the affected (workspace, ai_tool, period) key.

Columns:
- ``id`` — matches the reservation_id used as the Redis hash field.
- ``workspace_id`` — FK to workspaces, CASCADE on delete.
- ``ai_tool`` — NULL for workspace-wide (matches the "_all" bucket
  the ledger uses in Redis keys).
- ``period_key`` — YYYY-MM. Matches ``_current_period_start`` in the
  existing spend enforcement path so the reconciler can align.
- ``estimated_cents`` / ``actual_cents`` — estimated at reserve time,
  actual populated at commit.
- ``status`` — 'open' | 'released' | 'committed'.
- ``resolved_at`` — set at release/commit; NULL for open rows.

Indexes:
- ``ix_budget_reservations_open`` — partial index on open rows only,
  the exact query the reconciler runs.
- ``ix_budget_reservations_created_at`` — for retention/cleanup
  sweeps.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0138"
down_revision = "0137"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "budget_reservations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ai_tool", sa.Text(), nullable=True),
        sa.Column("period_key", sa.Text(), nullable=False),
        sa.Column("estimated_cents", sa.Integer(), nullable=False),
        sa.Column("actual_cents", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('open', 'released', 'committed')",
            name="ck_budget_reservations_status",
        ),
    )
    op.create_index(
        "ix_budget_reservations_open",
        "budget_reservations",
        ["workspace_id", "period_key"],
        postgresql_where=sa.text("status = 'open'"),
    )
    op.create_index(
        "ix_budget_reservations_created_at",
        "budget_reservations",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_budget_reservations_created_at", table_name="budget_reservations")
    op.drop_index("ix_budget_reservations_open", table_name="budget_reservations")
    op.drop_table("budget_reservations")
