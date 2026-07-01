"""add agent_identity_required to workflows

Revision ID: 0046
Revises: 0045
Create Date: 2026-07-01

"""

from alembic import op
import sqlalchemy as sa

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflows",
        sa.Column(
            "agent_identity_required",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )


def downgrade() -> None:
    op.drop_column("workflows", "agent_identity_required")
