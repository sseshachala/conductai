"""cred_retrieval_tokens — run-scoped credential broker tokens

Revision ID: 0071
Revises: 0070
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ARRAY, TEXT

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "cred_retrieval_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("token", sa.Text, nullable=False, unique=True),
        sa.Column("run_id", sa.Text, nullable=False),
        sa.Column("workspace_id", sa.Text, nullable=False),
        sa.Column("environment_id", sa.Text, nullable=True),
        sa.Column("allowed_handles", ARRAY(TEXT), nullable=False, server_default="{}"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_cred_retrieval_tokens_token", "cred_retrieval_tokens", ["token"])
    op.create_index("ix_cred_retrieval_tokens_run_id", "cred_retrieval_tokens", ["run_id"])


def downgrade() -> None:
    op.drop_table("cred_retrieval_tokens")
