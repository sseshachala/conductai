"""Drop legacy_input_tokens / legacy_output_tokens / legacy_cost_microdollars
from llm_attempt_receipts (#2209 Tier 1 removal).

Shipped for Session 6 shadow-vs-legacy delta metrics. Post-cutover
(PR #2226 merged 2026-09-24) settlement is authoritative on
``calculated_cost_microdollars``, so nothing writes or reads the legacy
comparison columns any more. Drop them.

Hand-written per project rule; no auto-generate.
"""
from alembic import op

revision = "0151"
down_revision = "0150"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("llm_attempt_receipts", "legacy_input_tokens")
    op.drop_column("llm_attempt_receipts", "legacy_output_tokens")
    op.drop_column("llm_attempt_receipts", "legacy_cost_microdollars")


def downgrade() -> None:
    import sqlalchemy as sa

    op.add_column(
        "llm_attempt_receipts",
        sa.Column("legacy_input_tokens", sa.Integer, nullable=True),
    )
    op.add_column(
        "llm_attempt_receipts",
        sa.Column("legacy_output_tokens", sa.Integer, nullable=True),
    )
    op.add_column(
        "llm_attempt_receipts",
        sa.Column("legacy_cost_microdollars", sa.BigInteger, nullable=True),
    )
