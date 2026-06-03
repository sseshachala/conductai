import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class GuardConfig(Base):
    """One Guard config per workspace — workspace IS the Guard team."""

    __tablename__ = "guard_config"

    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    invite_code = Column(Text, nullable=False)
    slug = Column(Text, nullable=True)
    alert_channel = Column(String(100), nullable=True)
    notify_on_block = Column(Boolean, nullable=False, default=True)
    notify_on_budget = Column(Boolean, nullable=False, default=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(DateTime(timezone=True), nullable=True)


class GuardMemberConfig(Base):
    """Per-workspace CLI token for a Clerk user. Role is always read from workspace_users."""

    __tablename__ = "guard_member_config"

    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    clerk_user_id = Column(Text, nullable=False, primary_key=True)
    member_token = Column(Text, nullable=False)
    active = Column(Boolean, nullable=False, default=True)
    joined_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )


class GuardPolicy(Base):
    __tablename__ = "guard_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    rule_id = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    match_tool = Column(String(255), nullable=True)
    match_pattern = Column(String(500), nullable=True)
    match_path_pattern = Column(String(500), nullable=True)
    action = Column(String(20), nullable=False)
    message = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    builtin = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class GuardSession(Base):
    __tablename__ = "guard_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    clerk_user_id = Column(Text, nullable=True)
    user_email = Column(String(255), nullable=True)
    ai_tool = Column(String(50), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    ended_at = Column(DateTime(timezone=True), nullable=True)
    total_tokens_before = Column(Integer, nullable=False, default=0)
    total_tokens_after = Column(Integer, nullable=False, default=0)
    total_cost_usd = Column(Float, nullable=False, default=0.0)
    total_saved_usd = Column(Float, nullable=False, default=0.0)
    event_count = Column(Integer, nullable=False, default=0)
    violations_count = Column(Integer, nullable=False, default=0)


class GuardAuditEvent(Base):
    __tablename__ = "guard_audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    clerk_user_id = Column(Text, nullable=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("guard_sessions.id"), nullable=True)
    user_email = Column(String(255), nullable=True)
    ai_tool = Column(String(50), nullable=False)
    tool_call = Column(String(50), nullable=False)
    input_summary = Column(Text, nullable=True)
    decision = Column(String(20), nullable=False)
    rule_id = Column(String(100), nullable=True)
    rule_message = Column(Text, nullable=True)
    tokens_before = Column(Integer, nullable=True)
    tokens_after = Column(Integer, nullable=True)
    tokens_saved = Column(Integer, nullable=True)
    cost_usd_before = Column(Float, nullable=True)
    cost_usd_after = Column(Float, nullable=True)
    tool_use_id = Column(String(255), nullable=True, index=True)
    hook_session_id = Column(Text, nullable=True, index=True)  # raw string session_id from hook stdin
    conductai_run_id = Column(String(255), nullable=True)
    conductai_workflow = Column(String(255), nullable=True)
    ts = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    duration_ms = Column(Integer, nullable=True)


class GuardSpendBudget(Base):
    __tablename__ = "guard_spend_budgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    clerk_user_id = Column(Text, nullable=True)
    monthly_limit_usd = Column(Float, nullable=False)
    alert_threshold_pct = Column(Integer, nullable=False, default=80)
    hard_limit_usd = Column(Float, nullable=True)
    default_per_developer_usd = Column(Float, nullable=True)
    last_alert_pct_bucket = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
