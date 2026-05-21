"""add environments table and environment_id to integrations and workflows

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-21
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create environments table
    op.create_table(
        "environments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id"),
            nullable=False,
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("workspace_id", "name", name="uq_environments_workspace_name"),
    )

    # 2. Add environment_id to integrations
    op.add_column(
        "integrations",
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id"),
            nullable=True,
        ),
    )

    # 3. Add environment_id to workflows
    op.add_column(
        "workflows",
        sa.Column(
            "environment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environments.id"),
            nullable=True,
        ),
    )

    # 4. Drop the old single unique constraint on integrations
    op.drop_constraint("uq_integrations_workspace_handle", "integrations", type_="unique")

    # 5. Add partial unique indexes
    op.execute(
        """
        CREATE UNIQUE INDEX uq_integrations_global_handle
        ON integrations (workspace_id, handle)
        WHERE environment_id IS NULL
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_integrations_env_handle
        ON integrations (workspace_id, environment_id, handle)
        WHERE environment_id IS NOT NULL
        """
    )


def downgrade() -> None:
    # Remove partial indexes
    op.execute("DROP INDEX IF EXISTS uq_integrations_env_handle")
    op.execute("DROP INDEX IF EXISTS uq_integrations_global_handle")

    # Restore original unique constraint
    op.create_unique_constraint(
        "uq_integrations_workspace_handle", "integrations", ["workspace_id", "handle"]
    )

    # Drop environment_id columns
    op.drop_column("workflows", "environment_id")
    op.drop_column("integrations", "environment_id")

    # Drop environments table
    op.drop_table("environments")
