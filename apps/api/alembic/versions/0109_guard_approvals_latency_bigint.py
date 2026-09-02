"""guard_approval_requests.latency_ms → BIGINT (#1565).

The column stored a duration in milliseconds as INT32. For any approval row
that sat pending longer than ~24 days, the sweep-to-timed_out UPDATE
overflowed with ``psycopg2.errors.NumericValueOutOfRange`` and returned 500
from ``GET /guard/approvals`` — see #1565. Promote to BIGINT so the column
matches the semantic (a duration, not a bounded counter).

Revision ID: 0109
Revises: 0108
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0109"
down_revision = "0108"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "guard_approval_requests",
        "latency_ms",
        type_=sa.BigInteger(),
        existing_type=sa.Integer(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "guard_approval_requests",
        "latency_ms",
        type_=sa.Integer(),
        existing_type=sa.BigInteger(),
        existing_nullable=True,
    )
