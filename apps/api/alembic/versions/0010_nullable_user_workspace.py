"""make users.workspace_id nullable — workspace membership now via workspace_users

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-23
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("users", "workspace_id", nullable=True)


def downgrade() -> None:
    # Re-null rows that have no workspace before restoring NOT NULL
    op.execute("UPDATE users SET workspace_id = (SELECT id FROM workspaces LIMIT 1) WHERE workspace_id IS NULL")
    op.alter_column("users", "workspace_id", nullable=False)
