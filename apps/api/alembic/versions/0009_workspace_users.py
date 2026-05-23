"""add workspace_users join table and clerk_id to users

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-23
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add clerk_id to users so we can look up user by Clerk sub claim
    op.add_column("users", sa.Column("clerk_id", sa.String(255), nullable=True))
    op.create_index("ix_users_clerk_id", "users", ["clerk_id"], unique=False)

    # Many-to-many: one user can belong to multiple workspaces with a role in each
    op.create_table(
        "workspace_users",
        sa.Column("workspace_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("clerk_user_id", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="editor"),
        sa.Column("invited_by", sa.String(255), nullable=True),
        sa.Column("joined_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("workspace_id", "clerk_user_id"),
    )
    op.create_index("ix_workspace_users_clerk_user_id", "workspace_users", ["clerk_user_id"])

    # Backfill: for every existing workspace, add owner as admin member
    op.execute("""
        INSERT INTO workspace_users (workspace_id, clerk_user_id, role, joined_at)
        SELECT id, owner_id, 'admin', created_at
        FROM workspaces
        WHERE owner_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)


def downgrade() -> None:
    op.drop_table("workspace_users")
    op.drop_index("ix_users_clerk_id", table_name="users")
    op.drop_column("users", "clerk_id")
