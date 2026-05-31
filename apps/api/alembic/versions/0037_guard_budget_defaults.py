"""guard_budget_defaults

Revision ID: 0037
Revises: 0036
Create Date: 2026-05-31

"""
import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guard_spend_budgets",
        sa.Column("default_per_developer_usd", sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("guard_spend_budgets", "default_per_developer_usd")
