"""add gateway_profile_id to workflows (#2170)

Revision ID: 0146
Revises: 0145
Create Date: 2026-09-21

Workflow → published Gateway profile picker. Nullable during rollout
so existing workflows keep running. Enforcement in brain_block lands
in a later PR of the same epic.
"""

from alembic import op
import sqlalchemy as sa

revision = "0146"
down_revision = "0145"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflows",
        sa.Column("gateway_profile_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_workflows_gateway_profile_id",
        "workflows",
        "gateway_profiles",
        ["gateway_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_workflows_gateway_profile_id",
        "workflows",
        ["gateway_profile_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflows_gateway_profile_id", table_name="workflows")
    op.drop_constraint("fk_workflows_gateway_profile_id", "workflows", type_="foreignkey")
    op.drop_column("workflows", "gateway_profile_id")
