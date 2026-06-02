"""Drop guard_teams.conductai_workspace_id — dead column from 0035

conductai_org_id is kept (still used as fallback in _lookup_team).
workspace_id FK (0040) is the canonical link going forward.

Revision ID: 0048
Revises: 0047
"""
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("guard_teams", "conductai_workspace_id")


def downgrade() -> None:
    import sqlalchemy as sa
    op.add_column("guard_teams", sa.Column("conductai_workspace_id", sa.String(255), nullable=True))
