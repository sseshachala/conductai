"""add security role to workspace_users check constraint

Revision ID: 0041
Revises: 0040
Create Date: 2026-06-01
"""
from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ck_workspace_users_role", "workspace_users", type_="check")
    op.create_check_constraint(
        "ck_workspace_users_role",
        "workspace_users",
        "role IN ('admin', 'editor', 'security', 'viewer')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_workspace_users_role", "workspace_users", type_="check")
    op.create_check_constraint(
        "ck_workspace_users_role",
        "workspace_users",
        "role IN ('admin', 'editor', 'viewer')",
    )
