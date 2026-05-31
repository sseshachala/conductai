"""guard_team_org_id

Revision ID: 0036
Revises: 0035
Create Date: 2026-05-30

"""
from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("guard_teams", "conductai_workspace_id", new_column_name="conductai_org_id")


def downgrade():
    op.alter_column("guard_teams", "conductai_org_id", new_column_name="conductai_workspace_id")
