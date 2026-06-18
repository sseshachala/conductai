"""add personas to guard_config, guard_member_config, guard_policies

Each workspace (tenant) gets a default persona on guard_config.
Each member can have a per-developer persona override on guard_member_config.
Each rule gets persona_affinity — which personas include this rule.

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-17
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, TEXT

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_PERSONAS = ("conservative", "standard", "developer")


def upgrade() -> None:
    # ── guard_config: workspace-wide default persona ──────────────────────
    op.add_column(
        "guard_config",
        sa.Column("persona", sa.String(20), nullable=False, server_default="standard"),
    )

    # ── guard_member_config: per-developer override ───────────────────────
    # NULL = use workspace default persona
    op.add_column(
        "guard_member_config",
        sa.Column("persona", sa.String(20), nullable=True),
    )
    # 'user' = developer self-selected via conduct init
    # 'admin' = centrally assigned, developer cannot override
    op.add_column(
        "guard_member_config",
        sa.Column("assigned_by", sa.String(10), nullable=False, server_default="user"),
    )

    # ── guard_policies: which personas include this rule ──────────────────
    # Default: all three personas — preserves existing enforcement behaviour
    op.add_column(
        "guard_policies",
        sa.Column(
            "persona_affinity",
            ARRAY(TEXT),
            nullable=False,
            server_default="ARRAY['conservative','standard','developer']::text[]",
        ),
    )
    op.create_index(
        "ix_guard_policies_persona_affinity",
        "guard_policies",
        ["persona_affinity"],
        postgresql_using="gin",
    )

    # ── Backfill persona_affinity based on action ─────────────────────────
    # conservative: all rules (most restrictive)
    # standard:     block + catastrophic warn rules
    # developer:    only the truly catastrophic blocks
    #
    # Safe defaults per action — refined later via admin persona management:
    #   block  → conservative + standard + developer (catastrophic applies everywhere)
    #   warn   → conservative + standard (developer is audit-first, skips warns)
    #   audit  → all three (audit is additive, never restrictive)
    conn = op.get_bind()

    conn.execute(sa.text("""
        UPDATE guard_policies
        SET persona_affinity = ARRAY['conservative','standard','developer']::text[]
        WHERE action IN ('block', 'audit')
    """))

    conn.execute(sa.text("""
        UPDATE guard_policies
        SET persona_affinity = ARRAY['conservative','standard']::text[]
        WHERE action = 'warn'
    """))


def downgrade() -> None:
    op.drop_index("ix_guard_policies_persona_affinity", "guard_policies")
    op.drop_column("guard_policies", "persona_affinity")
    op.drop_column("guard_member_config", "assigned_by")
    op.drop_column("guard_member_config", "persona")
    op.drop_column("guard_config", "persona")
