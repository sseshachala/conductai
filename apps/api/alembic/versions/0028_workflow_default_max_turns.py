"""0028 workflow_default_max_turns — add default_max_turns to workflows

Revision ID: 0028
Revises: 0027
"""
from alembic import op
import sqlalchemy as sa

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workflows",
        sa.Column("default_max_turns", sa.Integer(), nullable=True),
    )


def downgrade():
    op.drop_column("workflows", "default_max_turns")
