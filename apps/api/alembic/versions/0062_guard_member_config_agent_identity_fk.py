"""guard_member_config: add agent_identity_id FK to agent_identities

Revision ID: 0062
Revises: 0061
Create Date: 2026-07-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0062"
down_revision = "0061"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "guard_member_config",
        sa.Column("agent_identity_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_guard_member_config_agent_identity",
        "guard_member_config",
        "agent_identities",
        ["agent_identity_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_guard_member_config_agent_identity_id",
        "guard_member_config",
        ["agent_identity_id"],
    )


def downgrade():
    op.drop_index("ix_guard_member_config_agent_identity_id", table_name="guard_member_config")
    op.drop_constraint("fk_guard_member_config_agent_identity", "guard_member_config", type_="foreignkey")
    op.drop_column("guard_member_config", "agent_identity_id")
