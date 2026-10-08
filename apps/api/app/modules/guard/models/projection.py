"""ConductGuard ORM models — projection intents/summaries, approval requests, inbox."""

import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.core.database import Base


class GuardProjectionIntent(Base):
    """Durable projection outbox row; Redis only carries its identifier contract."""

    __tablename__ = "guard_projection_intents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", name="fk_guard_projection_intents_workspace_id", ondelete="CASCADE"), nullable=False)
    source_kind = Column(String(32), nullable=False)
    source_id = Column(Text, nullable=False)
    source_version = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False)
    available_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    expires_at = Column(DateTime(timezone=True), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(String(500), nullable=True)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("workspace_id", "source_kind", "source_id", "source_version", name="uq_guard_projection_intent_source_version"),
        CheckConstraint("attempts >= 0", name="ck_guard_projection_intents_attempts"),
        CheckConstraint("max_attempts > 0", name="ck_guard_projection_intents_max_attempts"),
        CheckConstraint("status IN ('pending', 'processing', 'retry', 'completed', 'dead_letter', 'superseded', 'expired', 'missing')", name="ck_guard_projection_intents_status"),
        CheckConstraint("source_kind IN ('audit_event', 'rule', 'discovered_agent', 'audit_summary')", name="ck_guard_projection_intents_source_kind"),
        Index("ix_guard_projection_intents_pending", "available_at", "created_at", postgresql_where=sa.text("status IN ('pending', 'retry')")),
        Index("ix_guard_projection_intents_expires_at", "expires_at"),
        Index(
            "uq_guard_projection_intent_outstanding_summary",
            "workspace_id",
            "source_kind",
            "source_id",
            unique=True,
            postgresql_where=sa.text(
                "source_kind = 'audit_summary' AND status IN ('pending', 'retry')"
            ),
        ),
        Index("ix_guard_projection_intents_lease", "lease_expires_at", postgresql_where=sa.text("status = 'processing'")),
    )


class GuardProjectionSummary(Base):
    """Bounded, PII-free aggregate source for routine allowed activity."""

    __tablename__ = "guard_projection_summaries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", name="fk_guard_projection_summaries_workspace_id", ondelete="CASCADE"), nullable=False)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    dimension_key = Column(String(64), nullable=False)
    ai_tool = Column(String(50), nullable=False)
    tool_call = Column(String(255), nullable=False)
    rule_id = Column(String(255), nullable=False, default="")
    event_count = Column(Integer, nullable=False, default=0)
    version = Column(Integer, nullable=False, default=1)
    canonical_facts = Column(JSONB, nullable=False, default=dict)
    source_timestamp = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("workspace_id", "window_start", "dimension_key", name="uq_guard_projection_summary_window_dimension"),
        CheckConstraint("window_end > window_start", name="ck_guard_projection_summary_window"),
        CheckConstraint("event_count > 0", name="ck_guard_projection_summary_event_count"),
        CheckConstraint("version > 0", name="ck_guard_projection_summary_version"),
        CheckConstraint("expires_at > source_timestamp", name="ck_guard_projection_summary_expiry"),
        Index("ix_guard_projection_summaries_workspace_window", "workspace_id", "window_start"),
        Index("ix_guard_projection_summaries_expires_at", "expires_at"),
    )


class GuardApprovalRequest(Base):
    """HITL approval request created by a rule with action=approval (#1140).

    Surface-agnostic: created from the CLI/MCP hook, LLM proxy, or workflow
    runtime. When triggered inside a workflow, source_run_id/source_block_id
    link back so the decide endpoint can resume the paused run using the same
    approval_received run_event that DSL approve blocks already emit.
    """

    __tablename__ = "guard_approval_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)

    rule_id      = Column(String(200), nullable=False)
    rule_pack    = Column(String(100), nullable=True)
    rule_message = Column(Text, nullable=True)

    tool_name  = Column(String(100), nullable=True)
    tool_input = Column(JSONB, nullable=False, default=dict)

    requester_email       = Column(String(255), nullable=True)
    requester_user_id     = Column(String(255), nullable=True)
    requester_agent_ident = Column(String(255), nullable=True)

    surface    = Column(String(50), nullable=False, default="unknown")
    session_id = Column(String(255), nullable=True)

    __table_args__ = (
        Index("idx_guard_approvals_ws_status", "workspace_id", "status", "created_at"),
        Index("idx_guard_approvals_ws_requester", "workspace_id", "requester_email"),
        Index(
            "idx_guard_approvals_source_run", "source_run_id",
            postgresql_where=sa.text("source_run_id IS NOT NULL"),
        ),
        Index(
            "idx_guard_approvals_pending_timeout", "timeout_at",
            postgresql_where=sa.text("status = 'pending'"),
        ),
    )

    source_run_id   = Column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True)
    source_block_id = Column(String(255), nullable=True)

    approval_group = Column(String(100), nullable=True)
    approval_type  = Column(String(20), nullable=False, default="any_authorized")

    status             = Column(String(20), nullable=False, default="pending")
    decided_by_email   = Column(String(255), nullable=True)
    decided_by_user_id = Column(String(255), nullable=True)
    decided_reason     = Column(Text, nullable=True)
    decided_at         = Column(DateTime(timezone=True), nullable=True)
    latency_ms         = Column(BigInteger, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    timeout_at = Column(DateTime(timezone=True), nullable=False)


class GuardInbox(Base):
    """Dedup'd triage inbox for Guard enforcement outcomes.

    Populated by the AFTER INSERT trigger on guard_audit_events
    (migration 0122). Only blocked/warned/approved decisions land
    here — plain 'allowed' stays in the audit firehose.

    Dedup key = sha256(workspace_id || rule_id || source || LEFT(description, 200))
    computed in the trigger. Same key hits UPSERT: occurrences += 1,
    last_seen_at updated, latest_event_id pointer moves. Resolved
    rows auto-reopen on re-fire.

    See #1840 for the design; migration 0122 for the DDL + trigger.
    """
    __tablename__ = "guard_inbox"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id   = Column(UUID(as_uuid=True), nullable=False)
    dedup_key      = Column(Text, nullable=False)
    rule_id        = Column(Text, nullable=False)
    source         = Column(Text, nullable=False)
    severity       = Column(Text, nullable=False)
    description    = Column(Text, nullable=True)
    occurrences    = Column(Integer, nullable=False, default=1)
    first_seen_at  = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen_at   = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    status         = Column(Text, nullable=False, default="open")
    resolved_reason = Column(Text, nullable=True)
    resolved_note  = Column(Text, nullable=True)
    resolved_at    = Column(DateTime(timezone=True), nullable=True)
    resolved_by    = Column(Text, nullable=True)
    latest_event_id = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("workspace_id", "dedup_key", name="guard_inbox_workspace_dedup_uniq"),
        Index("guard_inbox_ws_status_last_seen_idx", "workspace_id", "status", sa.text("last_seen_at DESC")),
        Index("guard_inbox_ws_severity_last_seen_idx", "workspace_id", "severity", sa.text("last_seen_at DESC")),
    )
