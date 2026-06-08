"""add index on workflows(workspace_id, playbook_slug)

Revision ID: 0068
Revises: 0067
Create Date: 2026-06-08
"""
from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_workflows_workspace_playbook_slug",
        "workflows",
        ["workspace_id", "playbook_slug"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflows_workspace_playbook_slug", table_name="workflows")
