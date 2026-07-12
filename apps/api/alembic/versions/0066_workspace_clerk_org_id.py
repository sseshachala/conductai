"""workspaces: add clerk_org_id for Clerk org → workspace mapping

Revision ID: 0066
Revises: 0065
"""
from alembic import op
import sqlalchemy as sa

revision = "0066"
down_revision = "0065"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workspaces",
        sa.Column("clerk_org_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_workspaces_clerk_org_id",
        "workspaces",
        ["clerk_org_id"],
        unique=True,
        postgresql_where=sa.text("clerk_org_id IS NOT NULL"),
    )


def downgrade():
    op.drop_index("ix_workspaces_clerk_org_id", table_name="workspaces")
    op.drop_column("workspaces", "clerk_org_id")
