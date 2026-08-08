"""Evolve agent_identities from token record into proper identity record.

Additive migration. Adds owner_user_id, source metadata, lifecycle state,
certification cadence, and risk tier fields. Backfills existing rows with
safe defaults so nothing breaks.

Revision ID: 0090
Revises: 0089
Create Date: 2026-08-08
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0090"
down_revision = "0089"
branch_labels = None
depends_on = None


LIFECYCLE_STATES = ("active", "pending_review", "deactivated", "expired")
RISK_TIERS = ("tier_1", "tier_2", "tier_3")


def upgrade() -> None:
    op.add_column("agent_identities", sa.Column("source", sa.String(50), nullable=True))
    op.add_column("agent_identities", sa.Column("source_id", sa.String(255), nullable=True))
    op.add_column("agent_identities", sa.Column("platform_of_origin", sa.String(50), nullable=True))
    op.add_column("agent_identities", sa.Column("owner_user_id", sa.String(100), nullable=True))
    op.add_column("agent_identities", sa.Column("agent_role_id", sa.String(36), nullable=True))
    op.add_column("agent_identities", sa.Column("lifecycle_state", sa.String(20), nullable=True))
    op.add_column("agent_identities", sa.Column("last_certified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_identities", sa.Column("certification_cadence_days", sa.Integer(), nullable=True))
    op.add_column("agent_identities", sa.Column("risk_tier", sa.String(10), nullable=True))
    op.add_column("agent_identities", sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_identities", sa.Column("metadata_json", sa.JSON(), nullable=True))

    op.execute(
        """
        UPDATE agent_identities
        SET
            owner_user_id      = created_by_clerk_user_id,
            source             = COALESCE(provider, 'conduct'),
            platform_of_origin = 'registry',
            risk_tier          = 'tier_1',
            certification_cadence_days = 90,
            lifecycle_state    = CASE
                WHEN expires_at IS NOT NULL AND expires_at < NOW() THEN 'expired'
                ELSE 'active'
            END
        WHERE lifecycle_state IS NULL
        """
    )

    op.alter_column("agent_identities", "source", nullable=False, server_default="conduct")
    op.alter_column("agent_identities", "platform_of_origin", nullable=False, server_default="registry")
    op.alter_column("agent_identities", "lifecycle_state", nullable=False, server_default="active")
    op.alter_column("agent_identities", "risk_tier", nullable=False, server_default="tier_1")
    op.alter_column("agent_identities", "certification_cadence_days", nullable=False, server_default="90")

    op.create_check_constraint(
        "ck_agent_identities_lifecycle_state",
        "agent_identities",
        f"lifecycle_state IN {LIFECYCLE_STATES!r}",
    )
    op.create_check_constraint(
        "ck_agent_identities_risk_tier",
        "agent_identities",
        f"risk_tier IN {RISK_TIERS!r}",
    )

    op.create_index("ix_agent_identities_owner_user_id", "agent_identities", ["owner_user_id"])
    op.create_index("ix_agent_identities_source", "agent_identities", ["source"])
    op.create_index("ix_agent_identities_platform_of_origin", "agent_identities", ["platform_of_origin"])
    op.create_index("ix_agent_identities_lifecycle_state", "agent_identities", ["lifecycle_state"])
    op.create_index("ix_agent_identities_risk_tier", "agent_identities", ["risk_tier"])
    op.create_index(
        "ix_agent_identities_workspace_owner",
        "agent_identities",
        ["workspace_id", "owner_user_id"],
    )
    op.create_index(
        "ix_agent_identities_source_source_id",
        "agent_identities",
        ["workspace_id", "source", "source_id"],
        unique=True,
        postgresql_where=sa.text("source_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_agent_identities_source_source_id", table_name="agent_identities")
    op.drop_index("ix_agent_identities_workspace_owner", table_name="agent_identities")
    op.drop_index("ix_agent_identities_risk_tier", table_name="agent_identities")
    op.drop_index("ix_agent_identities_lifecycle_state", table_name="agent_identities")
    op.drop_index("ix_agent_identities_platform_of_origin", table_name="agent_identities")
    op.drop_index("ix_agent_identities_source", table_name="agent_identities")
    op.drop_index("ix_agent_identities_owner_user_id", table_name="agent_identities")

    op.drop_constraint("ck_agent_identities_risk_tier", "agent_identities")
    op.drop_constraint("ck_agent_identities_lifecycle_state", "agent_identities")

    op.drop_column("agent_identities", "metadata_json")
    op.drop_column("agent_identities", "deactivated_at")
    op.drop_column("agent_identities", "risk_tier")
    op.drop_column("agent_identities", "certification_cadence_days")
    op.drop_column("agent_identities", "last_certified_at")
    op.drop_column("agent_identities", "lifecycle_state")
    op.drop_column("agent_identities", "agent_role_id")
    op.drop_column("agent_identities", "owner_user_id")
    op.drop_column("agent_identities", "platform_of_origin")
    op.drop_column("agent_identities", "source_id")
    op.drop_column("agent_identities", "source")
