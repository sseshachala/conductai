"""add is_template and source columns to workflows

Revision ID: 0081
Revises: 0080
Create Date: 2026-06-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0081"
down_revision = "0080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflows",
        sa.Column(
            "is_template",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "workflows",
        sa.Column(
            "source",
            sa.String(32),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("workflows", "source")
    op.drop_column("workflows", "is_template")
