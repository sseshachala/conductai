"""ConductGuard ORM models — audit events, archive segments, retention holds."""

import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.core.database import Base


class GuardAuditEvent(Base):
    __tablename__ = "guard_audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    clerk_user_id = Column(Text, nullable=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("guard_sessions.id"), nullable=True)
    user_email = Column(String(255), nullable=True)
    ai_tool = Column(String(50), nullable=False)
    tool_call = Column(String(255), nullable=True)  # nullable: proxy rows have no tool name
    source = Column(String(20), nullable=False, default="hook")   # 'hook' | 'gateway' | 'mcp' | 'workflow'  ('proxy' = legacy, still present on rows pre-migration 0139)
    provider = Column(String(30), nullable=True)    # 'anthropic' | 'openai' | 'perplexity' (proxy only)
    model = Column(String(100), nullable=True)      # vendor model id (proxy only)
    input_summary = Column(Text, nullable=True)
    decision = Column(String(20), nullable=False)
    rule_id = Column(String(100), nullable=True)
    rule_message = Column(Text, nullable=True)
    tokens_before = Column(Integer, nullable=True)
    tokens_after = Column(Integer, nullable=True)
    tokens_saved = Column(Integer, nullable=True)
    cost_usd_before = Column(Float, nullable=True)
    cost_usd_after = Column(Float, nullable=True)
    tool_use_id = Column(Text, nullable=True, index=True)
    hook_session_id = Column(Text, nullable=True, index=True)  # raw string session_id from hook stdin
    conductai_run_id = Column(String(255), nullable=True)
    conductai_workflow = Column(String(255), nullable=True)
    conductai_workflow_id = Column(String(255), nullable=True)
    blast_radius = Column(JSONB, nullable=True)
    # Added by revision 0056 — model was missing these columns (#1284).
    os_info = Column(String(128), nullable=True)
    hostname = Column(String(255), nullable=True)
    ts = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    duration_ms = Column(Integer, nullable=True)
    execution_status = Column(String(20), nullable=True)   # success | error | timeout
    result_summary = Column(Text, nullable=True)
    # hash-chain integrity — do not UPDATE or DELETE rows, chain breaks
    previous_hash = Column(Text, nullable=True)
    entry_hash = Column(Text, nullable=True)
    policy_hash = Column(Text, nullable=True)  # version_hash from GuardPolicyCache at decision time
    # session goal set by `conduct session start`
    goal_id   = Column(String(255), nullable=True)
    goal_name = Column(String(255), nullable=True)
    # layered verdict envelope (#1150 phase 1) — nullable so pre-migration and
    # non-eval audit paths (auth, approval, guard block) stay as-is
    evaluated_rules = Column(JSONB, nullable=True)   # list of {rule_id, severity, action, message}
    defense_score   = Column(Integer, nullable=True)  # weighted aggregate across matched rules
    # PR B.6 (#1347) — persisted routing decision for LLM proxy calls.
    # Only populated when the caller sent a tier form ("balanced" etc.);
    # NULL when a concrete model ID was forwarded straight through.
    routing_meta    = Column(JSONB, nullable=True)
    # Added by revision 0102 (#1340) — was already read by _event_to_dict via
    # getattr hotfix (#1338). Declaring on ORM closes schema drift.
    # ondelete=SET NULL: audit history must survive identity deletion.
    agent_identity_id = Column(
        String(36),
        ForeignKey("agent_identities.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Added by revision 0116 — sha256 of a short-lived share token, present
    # only for trial-workspace blocks. Enables anonymous receipt lookup for
    # signup users who don't yet have a login; workspace rows leave it NULL.
    share_token_hash = Column(Text, nullable=True)
    # Added by revision 0131 — FastAPI request path so legacy /proxy/* vs
    # new /gateway/v1/* traffic is queryable directly from audit rows.
    # NULL for in-process callers that never had an HTTP route.
    route = Column(String(128), nullable=True)
    # Added by revision 0132 — Phase 1 of #1959 (durable inference audit).
    # The two-phase writer emits an 'accepted' row before inference and
    # 'finalize()'s it after. All five columns are nullable so Phase-0
    # single-phase writers and every historical row stay valid.
    request_id = Column(UUID(as_uuid=True), nullable=True)
    lifecycle_state = Column(String(20), nullable=True)  # accepted|finalized|orphaned|expired
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    finalized_at = Column(DateTime(timezone=True), nullable=True)
    lease_expires_at = Column(DateTime(timezone=True), nullable=True)

    # Full payload is in a verified archive; retain receipt/accounting facts and
    # original chain fields online so existing references and rollups survive.
    archive_segment_id = Column(UUID(as_uuid=True), nullable=True)

    __table_args__ = (
        Index("ix_guard_audit_events_source", "workspace_id", "source", "ts"),
        Index("ix_guard_audit_events_route", "route"),
        Index(
            "ux_guard_audit_events_request_id",
            "request_id",
            unique=True,
            postgresql_where=sa.text("request_id IS NOT NULL"),
        ),
        Index(
            "ix_guard_audit_events_accepted_lease",
            "workspace_id", "lease_expires_at",
            postgresql_where=sa.text("lifecycle_state = 'accepted'"),
        ),
        Index(
            "ix_guard_audit_events_provider",
            "workspace_id", "provider", "ts",
            postgresql_where=sa.text("provider IS NOT NULL"),
        ),
        Index("ix_guard_audit_events_entry_hash", "entry_hash"),
        Index(
            "ix_guard_audit_events_evaluated_rules_gin",
            "evaluated_rules",
            postgresql_using="gin",
        ),
        Index("ix_guard_audit_events_ws_ts", "workspace_id", sa.text("ts DESC")),
        Index("ix_guard_audit_events_agent_identity_id", "agent_identity_id"),
        Index(
            "ix_guard_audit_events_ws_identity_session",
            "workspace_id", "agent_identity_id", "hook_session_id",
            postgresql_include=["ts"],
            postgresql_where=sa.text(
                "agent_identity_id IS NOT NULL AND hook_session_id IS NOT NULL AND hook_session_id <> ''"
            ),
        ),
        Index("ix_guard_audit_events_ws_rule_ts","workspace_id", "rule_id", "ts"),
        Index("ix_guard_audit_events_ws_decision_ts", "workspace_id", "decision", "ts"),
        Index("ix_guard_audit_events_unarchived", "workspace_id", "ts", "id",
              postgresql_where=sa.text("archive_segment_id IS NULL")),
        sa.ForeignKeyConstraint(
            ["archive_segment_id", "workspace_id"],
            ["guard_audit_archive_segments.id", "guard_audit_archive_segments.workspace_id"],
            name="fk_guard_audit_event_archive_workspace", ondelete="RESTRICT",
        ),
    )

    @classmethod
    def budget_eligible(cls):
        """Clause excluding client-reported ``session_usage`` rows: estimates must never enforce or settle budgets."""
        return cls.tool_call.is_distinct_from("session_usage")


class GuardAuditArchiveSegment(Base):
    __tablename__ = "guard_audit_archive_segments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    ordinal = Column(BigInteger, nullable=False)
    manifest = Column(JSONB, nullable=False)
    manifest_hash = Column(String(64), nullable=False)
    signature = Column(String(64), nullable=False)
    archived_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        UniqueConstraint("workspace_id", "ordinal", name="uq_guard_archive_ordinal"),
        UniqueConstraint("workspace_id", "manifest_hash", name="uq_guard_archive_manifest"),
        UniqueConstraint("id", "workspace_id", name="uq_guard_archive_id_workspace"),
        CheckConstraint("ordinal > 0", name="ck_guard_archive_ordinal"),
    )


class GuardAuditRetentionHold(Base):
    __tablename__ = "guard_audit_retention_holds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    ends_at = Column(DateTime(timezone=True), nullable=True)
    reason = Column(String(500), nullable=False)
    active = Column(Boolean, nullable=False, default=True, server_default=sa.true())
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (CheckConstraint("ends_at IS NULL OR ends_at >= starts_at", name="ck_guard_hold_range"),)
