"""Add roles, permissions, role_permissions tables with seed data

Revision ID: 0044
Revises: 0043
Create Date: 2026-06-02
"""
from alembic import op
import sqlalchemy as sa

revision = '0044'
down_revision = '0043'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE roles (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE,
            name        TEXT NOT NULL,
            description TEXT,
            is_system   BOOLEAN NOT NULL DEFAULT false,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_roles_system_name ON roles (name) WHERE workspace_id IS NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_roles_workspace_name ON roles (workspace_id, name) WHERE workspace_id IS NOT NULL
    """)

    op.execute("""
        CREATE TABLE permissions (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name        TEXT UNIQUE NOT NULL,
            description TEXT
        )
    """)

    op.execute("""
        CREATE TABLE role_permissions (
            role_id       UUID NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            permission_id UUID NOT NULL REFERENCES permissions(id) ON DELETE CASCADE,
            PRIMARY KEY (role_id, permission_id)
        )
    """)

    # Seed permissions
    op.execute("""
        INSERT INTO permissions (name, description) VALUES
        ('platform.workflows.view',     'View workflows'),
        ('platform.workflows.edit',     'Create / edit / delete workflows'),
        ('platform.workflows.run',      'Trigger workflow runs'),
        ('platform.runs.view',          'View workflow runs'),
        ('platform.marketplace.browse', 'Browse marketplace'),
        ('platform.marketplace.install','Install from marketplace'),
        ('platform.eval.view',          'View eval / observability'),
        ('platform.workspace.edit',     'Edit workspace name and plan'),
        ('platform.members.manage',     'Invite, remove, and change member roles'),
        ('platform.credentials.manage', 'View, add, and delete credentials / environments'),
        ('platform.audit_log.view',     'View audit log'),
        ('guard.activity.view_all',     'View all members activity dashboard and log'),
        ('guard.activity.view_own',     'View own activity only'),
        ('guard.activity.export',       'Export activity CSV'),
        ('guard.spend.view_all',        'View all members spend'),
        ('guard.spend.view_own',        'View own spend'),
        ('guard.spend.budgets.edit',    'Set spending budgets'),
        ('guard.policies.view',         'View guard policies'),
        ('guard.policies.edit',         'Toggle, add, and delete guard policies'),
        ('guard.settings.edit',         'Edit Slack channel and notification settings')
    """)

    # Seed system roles
    op.execute("""
        INSERT INTO roles (name, description, is_system) VALUES
        ('admin',     'Workspace owner. Full access to everything.',                              true),
        ('security',  'Security persona. Full Guard write access. Platform read + credentials.',  true),
        ('developer', 'Builder. Creates and runs workflows. Guard read-only, own activity only.', true),
        ('viewer',    'Read-only observer. Cannot write anything.',                               true)
    """)

    # admin — all permissions
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'admin' AND r.workspace_id IS NULL
    """)

    # security
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'security' AND r.workspace_id IS NULL
          AND p.name IN (
            'platform.workflows.view','platform.runs.view','platform.marketplace.browse',
            'platform.eval.view','platform.credentials.manage','platform.audit_log.view',
            'guard.activity.view_all','guard.activity.view_own','guard.activity.export',
            'guard.spend.view_all','guard.spend.view_own',
            'guard.policies.view','guard.policies.edit'
          )
    """)

    # developer
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'developer' AND r.workspace_id IS NULL
          AND p.name IN (
            'platform.workflows.view','platform.workflows.edit','platform.workflows.run',
            'platform.runs.view','platform.marketplace.browse','platform.marketplace.install',
            'platform.eval.view',
            'guard.activity.view_own','guard.spend.view_own','guard.policies.view'
          )
    """)

    # viewer
    op.execute("""
        INSERT INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM roles r, permissions p
        WHERE r.name = 'viewer' AND r.workspace_id IS NULL
          AND p.name IN (
            'platform.workflows.view','platform.runs.view',
            'platform.marketplace.browse','platform.eval.view',
            'guard.activity.view_own','guard.policies.view'
          )
    """)


def downgrade():
    op.execute("DROP TABLE IF EXISTS role_permissions")
    op.execute("DROP TABLE IF EXISTS permissions")
    op.execute("DROP TABLE IF EXISTS roles")
