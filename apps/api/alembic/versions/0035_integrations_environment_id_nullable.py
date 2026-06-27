"""integrations.environment_id — allow NULL for workspace-level integrations

Revision ID: 0035_integrations_environment_id_nullable
Revises: 0034_workspace_config
Create Date: 2026-06-27
"""
from alembic import op

revision = "0035_integrations_environment_id_nullable"
down_revision = "0034_workspace_config"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Widen version_num so long revision IDs (>32 chars) fit
    op.execute("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128)")
    op.alter_column("integrations", "environment_id", nullable=True)


def downgrade() -> None:
    op.alter_column("integrations", "environment_id", nullable=False)
