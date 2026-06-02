"""Fix conduct_api_keys.role — rename editor→developer, add CHECK constraint

0043 renamed editor→developer in workspace_users and guard_members but missed
conduct_api_keys. Any API key created since 0021 has role='editor' by default,
a value that no longer exists in the role vocabulary.

Revision ID: 0046
Revises: 0045
"""
from alembic import op
import sqlalchemy as sa

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Rename stale values
    op.execute("UPDATE conduct_api_keys SET role = 'developer' WHERE role = 'editor'")
    op.execute("UPDATE workspace_invites SET role = 'developer' WHERE role = 'editor'")

    # 2. Fix server defaults
    op.alter_column("conduct_api_keys", "role", server_default="developer")
    op.alter_column("workspace_invites", "role", server_default="developer")

    # 3. Add CHECK constraints
    op.execute("""
        ALTER TABLE conduct_api_keys
        DROP CONSTRAINT IF EXISTS ck_conduct_api_keys_role
    """)
    op.create_check_constraint(
        "ck_conduct_api_keys_role",
        "conduct_api_keys",
        "role IN ('admin', 'security', 'developer', 'viewer')",
    )
    op.execute("""
        ALTER TABLE workspace_invites
        DROP CONSTRAINT IF EXISTS ck_workspace_invites_role
    """)
    op.create_check_constraint(
        "ck_workspace_invites_role",
        "workspace_invites",
        "role IN ('admin', 'security', 'developer', 'viewer')",
    )


def downgrade() -> None:
    op.execute("ALTER TABLE conduct_api_keys DROP CONSTRAINT IF EXISTS ck_conduct_api_keys_role")
    op.execute("ALTER TABLE workspace_invites DROP CONSTRAINT IF EXISTS ck_workspace_invites_role")
    op.alter_column("conduct_api_keys", "role", server_default="editor")
    op.alter_column("workspace_invites", "role", server_default="editor")
