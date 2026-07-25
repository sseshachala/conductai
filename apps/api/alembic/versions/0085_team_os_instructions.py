"""Add workspace_instructions table and instructions_version to guard_member_config.

Revision ID: 0085
Revises: 0084
Create Date: 2026-07-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0085"
down_revision = "0084"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_instructions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("version", sa.String(64), nullable=False, server_default="v1"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("updated_by", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_workspace_instructions_workspace_id",
        "workspace_instructions",
        ["workspace_id"],
        unique=True,
    )

    op.add_column(
        "guard_member_config",
        sa.Column("instructions_version", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("guard_member_config", "instructions_version")
    op.drop_index(
        "ix_workspace_instructions_workspace_id",
        table_name="workspace_instructions",
    )
    op.drop_table("workspace_instructions")
