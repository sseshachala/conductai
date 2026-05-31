"""guard_team_workspace_id

Revision ID: 0040
Revises: 0039
Create Date: 2026-05-31

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guard_teams",
        sa.Column("workspace_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_guard_teams_workspace_id",
        "guard_teams",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_guard_teams_workspace_id",
        "guard_teams",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_guard_teams_workspace_id", table_name="guard_teams")
    op.drop_constraint("fk_guard_teams_workspace_id", "guard_teams", type_="foreignkey")
    op.drop_column("guard_teams", "workspace_id")
