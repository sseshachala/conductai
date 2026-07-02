"""remove per-environment proxy_config integration rows

Proxy config is workspace-wide. Per-env rows caused PROXY_CONFIG_* keys to
appear in the environment env-vars list. Guard proxy reads the workspace-level
row directly; brain_block never reads proxy_config at all.

Revision ID: 0048
Revises: 0047
Create Date: 2026-07-01

"""

from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM integrations
        WHERE handle = 'proxy_config'
          AND environment_id IS NOT NULL
    """)


def downgrade() -> None:
    pass  # data-only migration, not reversible
