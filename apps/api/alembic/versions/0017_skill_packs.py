"""skill packs — SkillPack, WorkspaceSkillPack, GuardRuleOverride, GuardPolicyCache

Adds the four tables for the skill-pack model. Existing guard_policies rows
are preserved — this migration does NOT drop them. A separate seed script
(scripts/seed_skill_packs.py) migrates data and can be run after verifying
the new tables are correct.

Revision ID: 0017
Revises: 0016
Create Date: 2026-06-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "skill_packs",
        sa.Column("slug", sa.Text(), primary_key=True),
        sa.Column("version", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tier", sa.Text(), nullable=False, server_default="free"),
        sa.Column("rules", JSONB(), nullable=False, server_default="[]"),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )

    op.create_table(
        "workspace_skill_packs",
        sa.Column("workspace_id", sa.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("pack_slug", sa.Text(), primary_key=True),
        sa.Column("pinned_version", sa.Text(), nullable=True),
        sa.Column("installed_by", sa.Text(), nullable=True),
        sa.Column("installed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_workspace_skill_packs_workspace", "workspace_skill_packs", ["workspace_id"])

    op.create_table(
        "guard_rule_overrides",
        sa.Column("workspace_id", sa.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("rule_id", sa.Text(), primary_key=True),
        sa.Column("action", sa.Text(), nullable=True),
        sa.Column("disabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("custom_message", sa.Text(), nullable=True),
        sa.Column("overridden_by", sa.Text(), nullable=True),
        sa.Column("overridden_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index("ix_guard_rule_overrides_workspace", "guard_rule_overrides", ["workspace_id"])

    op.create_table(
        "guard_policy_cache",
        sa.Column("workspace_id", sa.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("persona", sa.Text(), primary_key=True),
        sa.Column("payload", JSONB(), nullable=False, server_default="[]"),
        sa.Column("version_hash", sa.Text(), nullable=False, server_default=""),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("guard_policy_cache")
    op.drop_index("ix_guard_rule_overrides_workspace", "guard_rule_overrides")
    op.drop_table("guard_rule_overrides")
    op.drop_index("ix_workspace_skill_packs_workspace", "workspace_skill_packs")
    op.drop_table("workspace_skill_packs")
    op.drop_table("skill_packs")
