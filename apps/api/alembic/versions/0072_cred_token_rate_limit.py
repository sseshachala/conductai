"""cred_retrieval_tokens — add used_count + max_uses for rate limiting

Revision ID: 0072
Revises: 0071
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0072"
down_revision = "0071"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cred_retrieval_tokens", sa.Column("used_count", sa.Integer, nullable=False, server_default="0"))
    op.add_column("cred_retrieval_tokens", sa.Column("max_uses", sa.Integer, nullable=False, server_default="10"))


def downgrade() -> None:
    op.drop_column("cred_retrieval_tokens", "used_count")
    op.drop_column("cred_retrieval_tokens", "max_uses")
