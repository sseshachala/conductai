"""drop proxy_config integration rows — replaced by env_vars PROXY_CONFIG_* keys

Revision ID: 0050
Revises: 0049
Create Date: 2026-07-02
"""
from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DELETE FROM integrations WHERE handle = 'proxy_config'")


def downgrade() -> None:
    pass  # data deletion is not reversible
