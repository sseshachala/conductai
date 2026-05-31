"""guard_member_token

Revision ID: 0038
Revises: 0037
Create Date: 2026-05-31

"""
import sqlalchemy as sa
from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guard_members",
        sa.Column("member_token", sa.String(64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_guard_members_member_token", "guard_members", ["member_token"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_guard_members_member_token", "guard_members", type_="unique")
    op.drop_column("guard_members", "member_token")
