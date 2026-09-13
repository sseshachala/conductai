"""canonical gateway profiles

Revision ID: 0127
Revises: 0126
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0127"
down_revision = "0126"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gateway_profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("environment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("schema_version", sa.String(length=16), nullable=False, server_default="1"),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("workspace_id", "environment_id", "name", name="uq_gateway_profiles_workspace_env_name"),
    )
    op.create_index("ix_gateway_profiles_workspace_id", "gateway_profiles", ["workspace_id"])
    op.create_index("ix_gateway_profiles_workspace_environment", "gateway_profiles", ["workspace_id", "environment_id"])


def downgrade() -> None:
    op.drop_index("ix_gateway_profiles_workspace_environment", table_name="gateway_profiles")
    op.drop_index("ix_gateway_profiles_workspace_id", table_name="gateway_profiles")
    op.drop_table("gateway_profiles")
