"""Add role_id FK to workspace_users — wire membership to normalized RBAC

Adds workspace_users.role_id referencing roles(id).
Backfills from the string role column by matching system roles (workspace_id IS NULL).
Column is nullable — string column stays as denormalized cache until all
code paths are migrated to read through the FK.

Revision ID: 0049
Revises: 0048
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_users",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_workspace_users_role_id",
        "workspace_users",
        "roles",
        ["role_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_workspace_users_role_id", "workspace_users", ["role_id"])

    # Backfill from string role — match system roles only (workspace_id IS NULL)
    op.execute("""
        UPDATE workspace_users wu
        SET role_id = r.id
        FROM roles r
        WHERE r.name = wu.role
          AND r.workspace_id IS NULL
    """)


def downgrade() -> None:
    op.drop_index("ix_workspace_users_role_id", table_name="workspace_users")
    op.drop_constraint("fk_workspace_users_role_id", "workspace_users", type_="foreignkey")
    op.drop_column("workspace_users", "role_id")
