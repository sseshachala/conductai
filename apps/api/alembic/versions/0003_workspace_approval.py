"""add is_approved to workspaces

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-08
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workspaces", sa.Column(
        "is_approved", sa.Boolean, nullable=False, server_default="false"
    ))
    # Dev workspace and any existing workspaces are pre-approved
    op.execute("UPDATE workspaces SET is_approved = true")


def downgrade() -> None:
    op.drop_column("workspaces", "is_approved")
