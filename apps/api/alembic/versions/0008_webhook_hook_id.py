"""add github_hook_id and github_hook_repo to workflows

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-22
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workflows", sa.Column("github_hook_id", sa.String(255), nullable=True))
    op.add_column("workflows", sa.Column("github_hook_repo", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("workflows", "github_hook_repo")
    op.drop_column("workflows", "github_hook_id")
