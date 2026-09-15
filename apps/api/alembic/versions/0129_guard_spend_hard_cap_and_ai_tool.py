"""guard_spend_budgets: add hard_cap_enabled flag and ai_tool scope.

- hard_cap_enabled: single workspace-global switch. When false on the
  workspace-default row, /guard/spend/budget-check always returns
  hard_blocked=False. Defaults to false so existing workspaces do not
  start enforcing at deploy time.
- ai_tool: nullable text. NULL preserves today's across-all-tools row.
  Non-NULL scopes a budget to a specific AI tool (matches the free-text
  values already stored in guard_audit_events.ai_tool).
- Partial unique indexes reworked to include COALESCE(ai_tool, '') so a
  workspace can hold one default row plus one row per tool.

Revision ID: 0129
Revises: 0128
"""
from alembic import op
import sqlalchemy as sa

revision = "0129"
down_revision = "0128"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "guard_spend_budgets",
        sa.Column("ai_tool", sa.Text(), nullable=True),
    )
    op.add_column(
        "guard_spend_budgets",
        sa.Column(
            "hard_cap_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Existing rows should reflect their prior enforcement state: if a
    # hard_limit_usd or default_per_developer_usd was set, the workspace
    # was already blocking at cap. Preserve that behavior in-place.
    op.execute(
        """
        UPDATE guard_spend_budgets
        SET hard_cap_enabled = true
        WHERE hard_limit_usd IS NOT NULL
           OR default_per_developer_usd IS NOT NULL
        """
    )

    op.drop_index("uq_guard_spend_workspace_default", table_name="guard_spend_budgets")
    op.drop_index("uq_guard_spend_workspace_member", table_name="guard_spend_budgets")

    op.create_index(
        "uq_guard_spend_workspace_default",
        "guard_spend_budgets",
        ["workspace_id", sa.text("COALESCE(ai_tool, '')")],
        unique=True,
        postgresql_where=sa.text("clerk_user_id IS NULL"),
    )
    op.create_index(
        "uq_guard_spend_workspace_member",
        "guard_spend_budgets",
        ["workspace_id", "clerk_user_id", sa.text("COALESCE(ai_tool, '')")],
        unique=True,
        postgresql_where=sa.text("clerk_user_id IS NOT NULL"),
    )


def downgrade():
    op.drop_index("uq_guard_spend_workspace_default", table_name="guard_spend_budgets")
    op.drop_index("uq_guard_spend_workspace_member", table_name="guard_spend_budgets")

    op.create_index(
        "uq_guard_spend_workspace_default",
        "guard_spend_budgets",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("clerk_user_id IS NULL"),
    )
    op.create_index(
        "uq_guard_spend_workspace_member",
        "guard_spend_budgets",
        ["workspace_id", "clerk_user_id"],
        unique=True,
        postgresql_where=sa.text("clerk_user_id IS NOT NULL"),
    )

    op.drop_column("guard_spend_budgets", "hard_cap_enabled")
    op.drop_column("guard_spend_budgets", "ai_tool")
