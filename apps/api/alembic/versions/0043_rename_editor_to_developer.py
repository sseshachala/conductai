"""rename editor to developer in workspace_users; add CHECK constraints

Revision ID: 0043
Revises: 0042
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = '0043'
down_revision = '0042'
branch_labels = None
depends_on = None


def upgrade():
    # Drop any pre-existing role constraints so UPDATE and re-create can succeed
    # (handles partial previous migration runs)
    op.execute("ALTER TABLE workspace_users DROP CONSTRAINT IF EXISTS ck_workspace_users_role")
    op.execute("ALTER TABLE guard_members DROP CONSTRAINT IF EXISTS ck_guard_members_role")

    # 1. Rename owner -> admin in guard_members (safety sweep; none expected in prod)
    op.execute("UPDATE guard_members SET role = 'admin' WHERE role = 'owner'")

    # 2. Rename editor -> developer in workspace_users
    op.execute("UPDATE workspace_users SET role = 'developer' WHERE role = 'editor'")

    # 3. CHECK constraint on workspace_users.role
    op.create_check_constraint(
        "ck_workspace_users_role",
        "workspace_users",
        "role IN ('admin', 'security', 'developer', 'viewer')",
    )

    # 4. CHECK constraint on guard_members.role
    op.create_check_constraint(
        "ck_guard_members_role",
        "guard_members",
        "role IN ('admin', 'security', 'developer', 'viewer')",
    )


def downgrade():
    # Remove CHECK constraints
    op.drop_constraint("ck_guard_members_role", "guard_members", type_="check")
    op.drop_constraint("ck_workspace_users_role", "workspace_users", type_="check")

    # Reverse renames
    op.execute("UPDATE workspace_users SET role = 'editor' WHERE role = 'developer'")
    op.execute("UPDATE guard_members SET role = 'owner' WHERE role = 'admin'")
