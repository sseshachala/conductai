"""Add share_token_hash to guard_audit_events for anonymous trial receipts (#1712 Track 1).

Column is nullable and stays NULL for workspace-authenticated blocks. Trial
blocks store sha256(cond_bkr_*) so an anonymous signup user can view their
own block receipt via /api/guard/blocks/public/{id}/{token}.

Revision ID: 0116
Revises: 0115
Create Date: 2026-09-07
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0116"
down_revision = "0115"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "guard_audit_events",
        sa.Column("share_token_hash", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("guard_audit_events", "share_token_hash")
