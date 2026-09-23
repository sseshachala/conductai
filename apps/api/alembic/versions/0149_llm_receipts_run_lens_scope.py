"""Add workflow_run / workflow_step / hook_session scope to llm_attempt_receipts.

Session 5 of #2209 wires the shadow writer into workflow-runtime and Lens
call paths. Aggregations like "cost per workflow run" or "Lens session
spend" need explicit scope columns; adding them here (nullable, indexed
partial WHERE NOT NULL) keeps existing rows untouched and lets Session 6+
queries answer those questions from the shared engine.

Hand-written per project rule; every constraint / index has an explicit name.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0149"
down_revision = "0148"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_attempt_receipts",
        sa.Column("workflow_run_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "llm_attempt_receipts",
        sa.Column("workflow_step_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "llm_attempt_receipts",
        sa.Column("hook_session_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_llm_attempt_receipts_workflow_run",
        "llm_attempt_receipts",
        ["workflow_run_id"],
        postgresql_where=sa.text("workflow_run_id IS NOT NULL"),
    )
    op.create_index(
        "ix_llm_attempt_receipts_hook_session",
        "llm_attempt_receipts",
        ["hook_session_id"],
        postgresql_where=sa.text("hook_session_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_llm_attempt_receipts_hook_session",
        table_name="llm_attempt_receipts",
    )
    op.drop_index(
        "ix_llm_attempt_receipts_workflow_run",
        table_name="llm_attempt_receipts",
    )
    op.drop_column("llm_attempt_receipts", "hook_session_id")
    op.drop_column("llm_attempt_receipts", "workflow_step_id")
    op.drop_column("llm_attempt_receipts", "workflow_run_id")
