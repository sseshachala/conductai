"""Guard rate limits — per-key RPM/TPM caps (#980, Loopers parity).

Introduces `guard_rate_limits`: workspace-default row (agent_identity_id NULL)
+ optional per-agent overrides. Enforcement lives in
`app.modules.guard.rate_limit.check_rate_limit` and is called from `_proxy`
step 4d.2 after the budget check.

Revision ID: 0096
Revises: 0095
Create Date: 2026-08-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID


revision = "0096"
down_revision = "0095"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guard_rate_limits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_identity_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_identities.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("rpm", sa.Integer, nullable=True),
        sa.Column("tpm", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("workspace_id", "agent_identity_id", name="uq_guard_rate_limits_scope"),
    )
    op.create_index(
        "idx_guard_rate_limits_ws",
        "guard_rate_limits",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_guard_rate_limits_ws", table_name="guard_rate_limits")
    op.drop_table("guard_rate_limits")
