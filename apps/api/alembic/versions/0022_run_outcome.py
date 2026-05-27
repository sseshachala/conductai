"""0022 run outcome column

Adds outcome JSONB to the runs table so the executor can write explicit
semantic outcomes (pr_opened, issue_triaged, review_completed, …) instead of
relying on Dashboard heuristics over run.state.

NULL on all existing rows — Dashboard COALESCEs with the old heuristic.

Revision ID: 0022
Revises: 0021
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("runs", sa.Column("outcome", JSONB, nullable=True))


def downgrade():
    op.drop_column("runs", "outcome")
