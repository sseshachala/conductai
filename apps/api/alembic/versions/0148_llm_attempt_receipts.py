"""LlmAttemptReceipt — per-attempt accounting shadow table (#2209 Session 4).

Distinct from ``guard_audit_events`` (enforced one-row-per-request via
``ux_guard_audit_events_request_id``). This table supports N rows per
request through the ``(request_id, attempt_ordinal)`` unique key so retries
and fallbacks can each carry their own receipt.

Written in shadow mode by ``app.runtime.accounting.shadow_writer`` — old
settlement remains authoritative until Session 6 activation. Session 7
retires the legacy path.

Hand-written per project rule — no ``alembic revision --autogenerate``.
Every constraint / index has an explicit ``name=`` so SQLAlchemy and
Postgres agree on identifiers.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0148"
down_revision = "0147"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llm_attempt_receipts",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
        ),
        sa.Column(
            "workspace_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "workspaces.id",
                ondelete="CASCADE",
                name="fk_llm_attempt_receipts_workspace",
            ),
            nullable=False,
        ),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "attempt_ordinal",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("parent_receipt_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("contract_version", sa.Integer(), nullable=False),
        sa.Column("developer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("agent_identity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("client_tool", sa.Text(), nullable=True),
        sa.Column("transport", sa.Text(), nullable=True),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("model_alias", sa.Text(), nullable=True),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("execution_outcome", sa.Text(), nullable=False),
        sa.Column("total_input_tokens", sa.Integer(), nullable=True),
        sa.Column("total_output_tokens", sa.Integer(), nullable=True),
        sa.Column("uncached_input_tokens", sa.Integer(), nullable=True),
        sa.Column("cache_read_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "cache_write_tokens_by_tier",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("reasoning_output_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "modality_units",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("usage_origin", sa.Text(), nullable=False),
        sa.Column("usage_completeness", sa.Text(), nullable=False),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=True),
        sa.Column("reserved_microdollars", sa.BigInteger(), nullable=True),
        sa.Column("calculated_cost_microdollars", sa.BigInteger(), nullable=True),
        sa.Column(
            "currency",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'USD'"),
        ),
        sa.Column("pricing_version", sa.Text(), nullable=True),
        sa.Column("pricing_completeness", sa.Text(), nullable=False),
        # Shadow-comparison fields. NULLable — Session 6 metrics compare with
        # the equivalent GuardAuditEvent row for the same request_id.
        sa.Column("legacy_input_tokens", sa.Integer(), nullable=True),
        sa.Column("legacy_output_tokens", sa.Integer(), nullable=True),
        sa.Column("legacy_cost_microdollars", sa.BigInteger(), nullable=True),
        sa.Column("normalizer_version", sa.Text(), nullable=True),
        sa.Column(
            "calculation_provenance",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "finalized_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "request_id",
            "attempt_ordinal",
            name="ux_llm_attempt_receipts_request_attempt",
        ),
    )
    op.create_index(
        "ix_llm_attempt_receipts_ws_finalized",
        "llm_attempt_receipts",
        ["workspace_id", "finalized_at"],
    )
    op.create_index(
        "ix_llm_attempt_receipts_request_id",
        "llm_attempt_receipts",
        ["request_id"],
    )
    op.create_index(
        "ix_llm_attempt_receipts_parent_receipt_id",
        "llm_attempt_receipts",
        ["parent_receipt_id"],
        postgresql_where=sa.text("parent_receipt_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_llm_attempt_receipts_parent_receipt_id",
        table_name="llm_attempt_receipts",
    )
    op.drop_index("ix_llm_attempt_receipts_request_id", table_name="llm_attempt_receipts")
    op.drop_index("ix_llm_attempt_receipts_ws_finalized", table_name="llm_attempt_receipts")
    op.drop_table("llm_attempt_receipts")
