"""0025 webhook hook label — track which label each workflow listens for

Adds github_hook_label to workflows so the webhook registration logic can
enforce: same (repo, event-type, label) = conflict; different labels = share
the same GitHub hook_id.

Revision ID: 0025
Revises: 0024
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workflows",
        sa.Column("github_hook_label", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_workflows_hook_label",
        "workflows",
        ["github_hook_repo", "github_hook_label"],
        postgresql_where=sa.text("github_hook_label IS NOT NULL"),
    )


def downgrade():
    op.drop_index("ix_workflows_hook_label", table_name="workflows")
    op.drop_column("workflows", "github_hook_label")
