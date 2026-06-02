"""Backfill guard_teams.workspace_id for teams where conductai_org_id matches workspace owner

0040 only caught teams where conductai_org_id was already a workspace UUID.
Teams created with a Clerk user sub as conductai_org_id were skipped.

Revision ID: 0045
Revises: 0044
"""
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        UPDATE guard_teams gt
        SET workspace_id = w.id
        FROM workspaces w
        WHERE gt.workspace_id IS NULL
          AND w.owner_id = gt.conductai_org_id
    """)


def downgrade() -> None:
    pass
