"""Add missing unique constraints and workspace_invites status/expiry

guard_policies:        UNIQUE(team_id, rule_id) — prevents duplicate rules per team
guard_spend_budgets:   partial uniques — one team-default row, one per-member row
workspace_invites:     add status + expires_at columns

Revision ID: 0047
Revises: 0046
"""
from alembic import op
import sqlalchemy as sa

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── guard_policies: UNIQUE(team_id, rule_id) ─────────────────────────────
    # Deduplicate first — keep the most recently created row per (team_id, rule_id)
    op.execute("""
        DELETE FROM guard_policies a
        USING guard_policies b
        WHERE a.id < b.id
          AND a.team_id = b.team_id
          AND a.rule_id = b.rule_id
    """)
    op.create_index(
        "uq_guard_policies_team_rule",
        "guard_policies",
        ["team_id", "rule_id"],
        unique=True,
    )

    # ── guard_spend_budgets: partial uniques ─────────────────────────────────
    # Deduplicate team-default rows (member_id IS NULL) — keep most recent
    op.execute("""
        DELETE FROM guard_spend_budgets a
        USING guard_spend_budgets b
        WHERE a.id < b.id
          AND a.team_id = b.team_id
          AND a.member_id IS NULL
          AND b.member_id IS NULL
    """)
    # Deduplicate per-member rows
    op.execute("""
        DELETE FROM guard_spend_budgets a
        USING guard_spend_budgets b
        WHERE a.id < b.id
          AND a.team_id = b.team_id
          AND a.member_id = b.member_id
          AND a.member_id IS NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_guard_spend_team_default
        ON guard_spend_budgets (team_id)
        WHERE member_id IS NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_guard_spend_team_member
        ON guard_spend_budgets (team_id, member_id)
        WHERE member_id IS NOT NULL
    """)

    # ── workspace_invites: status + expires_at ───────────────────────────────
    op.add_column(
        "workspace_invites",
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "workspace_invites",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill status from accepted_at
    op.execute("""
        UPDATE workspace_invites
        SET status = 'accepted'
        WHERE accepted_at IS NOT NULL
    """)
    op.create_check_constraint(
        "ck_workspace_invites_status",
        "workspace_invites",
        "status IN ('pending', 'accepted', 'revoked', 'expired')",
    )


def downgrade() -> None:
    op.execute("ALTER TABLE workspace_invites DROP CONSTRAINT IF EXISTS ck_workspace_invites_status")
    op.drop_column("workspace_invites", "expires_at")
    op.drop_column("workspace_invites", "status")
    op.execute("DROP INDEX IF EXISTS uq_guard_spend_team_member")
    op.execute("DROP INDEX IF EXISTS uq_guard_spend_team_default")
    op.drop_index("uq_guard_policies_team_rule", table_name="guard_policies")
