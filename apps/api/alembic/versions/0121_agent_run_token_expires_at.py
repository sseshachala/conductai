"""add expires_at to agent_run_tokens (audit S04)

Bounded lifetime for run tokens so an abandoned/leaked token can't
authenticate forever. Executor mints with `created_at + 24h` going
forward; backfill existing rows the same way so the NOT NULL constraint
lands safely.

Revision ID: 0121
Revises: 0120
Create Date: 2026-09-11
"""
from alembic import op
import sqlalchemy as sa

revision = "0121"
down_revision = "0120"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add nullable first so existing rows keep validating.
    op.add_column(
        "agent_run_tokens",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill: created_at + 24h. Existing runs older than 24h now have
    # tokens that will start rejecting on next use — that's the intent,
    # a token from a run that finished last week has no business
    # authenticating today.
    op.execute(
        "UPDATE agent_run_tokens SET expires_at = created_at + INTERVAL '24 hours' WHERE expires_at IS NULL"
    )
    op.alter_column("agent_run_tokens", "expires_at", nullable=False)
    op.create_index(
        "ix_agent_run_tokens_expires_at",
        "agent_run_tokens",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_run_tokens_expires_at", table_name="agent_run_tokens")
    op.drop_column("agent_run_tokens", "expires_at")
