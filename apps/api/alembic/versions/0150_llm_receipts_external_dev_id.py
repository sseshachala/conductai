"""Add developer_external_id to llm_attempt_receipts (#2209 Session 6c).

Reviewer finding #1 on #2221: Gateway and Lens callers pass Clerk IDs,
emails, and ``"system:lens"`` sentinel strings into ``developer_user_id``
(a UUID column). SQLAlchemy silently rejected the insert and the whole
receipt was dropped.

Fix: keep ``developer_user_id`` for a resolved internal user UUID (still
nullable, filled by future work that maps Clerk → User); add
``developer_external_id: Text NULL`` for the untyped identifier the
callers actually have.

Hand-written per project rule; explicit index name.
"""
from alembic import op
import sqlalchemy as sa

revision = "0150"
down_revision = "0149"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_attempt_receipts",
        sa.Column("developer_external_id", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_llm_attempt_receipts_developer_external_id",
        "llm_attempt_receipts",
        ["developer_external_id"],
        postgresql_where=sa.text("developer_external_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_llm_attempt_receipts_developer_external_id",
        table_name="llm_attempt_receipts",
    )
    op.drop_column("llm_attempt_receipts", "developer_external_id")
