"""R9 (reviewer P1) — end-to-end microdollar precision.

Reviewer R9: each $0.004 request settled as zero cents because the
enforcement counter was integer cents. Aggregated small paid requests
never advanced the live committed counter even though the aggregate
cost was material.

Fix (this migration, part 1): add BIGINT ``estimated_micros`` and
``actual_micros`` columns to ``budget_reservations``. One micro-dollar
is 10^-6 USD, so 1 cent = 10 000 micros and $0.004 = 4 000 micros —
precise enough to accumulate correctly against any real cap.

Backfill scales existing cents-mode data by 10 000 so historical rows
sit at the same nominal value in the new unit. Old cents columns stay
in place; the ledger prefers micros when populated, falls back to
cents × 10 000 for legacy callers. A future migration will drop the
cents columns once every caller has switched.
"""
from alembic import op
import sqlalchemy as sa


revision = "0144"
down_revision = "0143"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "budget_reservations",
        sa.Column("estimated_micros", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "budget_reservations",
        sa.Column("actual_micros", sa.BigInteger(), nullable=True),
    )
    # Backfill existing rows: cents * 10_000 = micros.
    op.execute(
        "UPDATE budget_reservations "
        "SET estimated_micros = estimated_cents * 10000 "
        "WHERE estimated_micros IS NULL AND estimated_cents IS NOT NULL"
    )
    op.execute(
        "UPDATE budget_reservations "
        "SET actual_micros = actual_cents * 10000 "
        "WHERE actual_micros IS NULL AND actual_cents IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("budget_reservations", "actual_micros")
    op.drop_column("budget_reservations", "estimated_micros")
