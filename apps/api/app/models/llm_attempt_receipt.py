"""LlmAttemptReceipt — one row per actual upstream LLM attempt (#2209 Session 4).

Storage for the shared accounting contract (``runtime.accounting.contracts``).
Distinct from ``GuardAuditEvent`` — which is enforced one-row-per-request via
``ux_guard_audit_events_request_id``. This table can hold N rows per request
(retries, fallbacks) via the ``(request_id, attempt_ordinal)`` unique key.

Session 4 wires ONE row per request at settlement time (matching current
GuardAuditEvent granularity) so shadow calculation runs end-to-end. Session 5
or 6 expands to true per-attempt writes once the coordinator captures
per-attempt usage bytes.

Rows are written in **shadow mode** by default — the writer catches every
exception. Old settlement (``GuardAuditEvent``) remains authoritative.
"""
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Column,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class LlmAttemptReceipt(Base):
    """One receipt per actual upstream LLM attempt.

    Contract-versioned. Historical rows are pinned to the version that wrote
    them; readers dispatch on ``contract_version`` when the shape evolves.
    """

    __tablename__ = "llm_attempt_receipts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE", name="fk_llm_attempt_receipts_workspace"),
        nullable=False,
    )
    request_id = Column(UUID(as_uuid=True), nullable=False)
    attempt_ordinal = Column(Integer, nullable=False, server_default=sa.text("0"))
    parent_receipt_id = Column(UUID(as_uuid=True), nullable=True)

    contract_version = Column(Integer, nullable=False)

    developer_user_id = Column(UUID(as_uuid=True), nullable=True)
    agent_identity_id = Column(UUID(as_uuid=True), nullable=True)
    workflow_run_id = Column(UUID(as_uuid=True), nullable=True)
    workflow_step_id = Column(UUID(as_uuid=True), nullable=True)
    hook_session_id = Column(UUID(as_uuid=True), nullable=True)
    source = Column(Text, nullable=True)
    client_tool = Column(Text, nullable=True)
    transport = Column(Text, nullable=True)

    provider = Column(Text, nullable=False)
    model = Column(Text, nullable=False)
    model_alias = Column(Text, nullable=True)
    operation = Column(Text, nullable=False)
    execution_outcome = Column(Text, nullable=False)

    total_input_tokens = Column(Integer, nullable=True)
    total_output_tokens = Column(Integer, nullable=True)
    uncached_input_tokens = Column(Integer, nullable=True)
    cache_read_tokens = Column(Integer, nullable=True)
    cache_write_tokens_by_tier = Column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )
    reasoning_output_tokens = Column(Integer, nullable=True)
    modality_units = Column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))

    usage_origin = Column(Text, nullable=False)
    usage_completeness = Column(Text, nullable=False)

    estimated_input_tokens = Column(Integer, nullable=True)
    reserved_microdollars = Column(BigInteger, nullable=True)
    calculated_cost_microdollars = Column(BigInteger, nullable=True)
    currency = Column(Text, nullable=False, server_default=sa.text("'USD'"))
    pricing_version = Column(Text, nullable=True)
    pricing_completeness = Column(Text, nullable=False)

    # Shadow-comparison columns. Populated with what the legacy code path
    # computed for the same attempt so Session 6 metrics can quantify the
    # delta by provider / model / cache / outcome before Session 7 activation.
    legacy_input_tokens = Column(Integer, nullable=True)
    legacy_output_tokens = Column(Integer, nullable=True)
    legacy_cost_microdollars = Column(BigInteger, nullable=True)

    normalizer_version = Column(Text, nullable=True)
    calculation_provenance = Column(
        JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")
    )

    started_at = Column(sa.DateTime(timezone=True), nullable=True)
    finalized_at = Column(
        sa.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "attempt_ordinal",
            name="ux_llm_attempt_receipts_request_attempt",
        ),
        Index(
            "ix_llm_attempt_receipts_ws_finalized",
            "workspace_id",
            "finalized_at",
        ),
        Index(
            "ix_llm_attempt_receipts_request_id",
            "request_id",
        ),
        Index(
            "ix_llm_attempt_receipts_parent_receipt_id",
            "parent_receipt_id",
            postgresql_where=sa.text("parent_receipt_id IS NOT NULL"),
        ),
        Index(
            "ix_llm_attempt_receipts_workflow_run",
            "workflow_run_id",
            postgresql_where=sa.text("workflow_run_id IS NOT NULL"),
        ),
        Index(
            "ix_llm_attempt_receipts_hook_session",
            "hook_session_id",
            postgresql_where=sa.text("hook_session_id IS NOT NULL"),
        ),
    )
