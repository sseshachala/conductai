"""workspace_custom_rules — per-workspace custom guard rules (replaces guard_policies)

Creates the new table that holds custom (non-pack) rules a workspace defines.
Pack-installed rules continue to live in skill_packs.rules JSONB and are
resolved via compute_policy(). This table holds only the rules a workspace
created itself.

Includes an inline backfill from guard_policies for any custom rows
(builtin=False AND pack_id IS NULL AND archived_at IS NULL). The full DROP
of guard_policies happens in a later migration once the application is fully
cut over to compute_policy() + workspace_custom_rules.

Revision ID: 0023
Revises: 0022
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_custom_rules",
        sa.Column("workspace_id", sa.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("rule_id", sa.Text(), primary_key=True),
        sa.Column("body", JSONB(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_workspace_custom_rules_workspace", "workspace_custom_rules", ["workspace_id"])

    # Backfill from guard_policies: custom rules only (builtin=False, pack_id IS NULL).
    # Idempotent: ON CONFLICT DO NOTHING.
    op.execute("""
        INSERT INTO workspace_custom_rules (workspace_id, rule_id, body, enabled, created_at, updated_at)
        SELECT
            workspace_id,
            rule_id,
            jsonb_strip_nulls(jsonb_build_object(
                'id',                  rule_id,
                'description',         description,
                'match_tool',          match_tool,
                'match_pattern',       match_pattern,
                'match_path_pattern',  match_path_pattern,
                'match_tokens_before_gt', match_tokens_before_gt,
                'action',              action,
                'message',             message,
                'persona_affinity',    to_jsonb(persona_affinity),
                'recommendation',      recommendation,
                'frameworks',          to_jsonb(frameworks),
                'severity',            severity,
                'iso_control',         iso_control
            )),
            enabled,
            created_at,
            updated_at
        FROM guard_policies
        WHERE builtin = false
          AND pack_id IS NULL
          AND archived_at IS NULL
        ON CONFLICT (workspace_id, rule_id) DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index("ix_workspace_custom_rules_workspace", "workspace_custom_rules")
    op.drop_table("workspace_custom_rules")
