"""drop guard_policies table — single source of truth is now skill_packs.rules JSONB

By the time this migration runs:
  - Custom rules (builtin=False, pack_id IS NULL) were already backfilled to
    workspace_custom_rules by migration 0023.
  - Pack-installed rules already live in skill_packs.rules JSONB (migration
    0017 + scripts/seed_skill_packs.py) and are resolved via compute_policy.
  - Disabled builtin rules are tracked in guard_rule_overrides.

So this migration only drops the table. The downgrade re-creates an empty
table with the same shape; the previous-state data is not restorable from
here — backups are the authoritative restore path.

Revision ID: 0024
Revises: 0023
Create Date: 2026-06-21
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("guard_policies")


def downgrade() -> None:
    op.create_table(
        "guard_policies",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("rule_id", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("match_tool", sa.String(255), nullable=True),
        sa.Column("match_pattern", sa.String(500), nullable=True),
        sa.Column("match_path_pattern", sa.String(500), nullable=True),
        sa.Column("match_tokens_before_gt", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("builtin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("pack_id", sa.String(100), nullable=True),
        sa.Column("persona_affinity", ARRAY(sa.Text()), nullable=False,
                  server_default="{conservative,standard,developer}"),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("frameworks", ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("severity", sa.String(20), nullable=False, server_default="medium"),
        sa.Column("iso_control", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )
