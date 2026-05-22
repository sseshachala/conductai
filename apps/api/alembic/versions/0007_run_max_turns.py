"""add max_turns to runs

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-22
"""
from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("max_turns", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "max_turns")
