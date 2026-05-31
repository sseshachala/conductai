import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class GuardTeam(Base):
    """One Guard team per Clerk org — spans all projects in the org."""

    __tablename__ = "guard_teams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), nullable=False, unique=True)
    invite_code = Column(String(32), nullable=False, unique=True)
    conductai_org_id = Column(String(255), nullable=True)
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


class GuardMember(Base):
    __tablename__ = "guard_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("guard_teams.id"), nullable=False)
    user_id = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="developer")
    active = Column(Boolean, nullable=False, default=True)
    joined_at = Column(DateTime(timezone=True), nullable=True)
    member_token = Column(String(64), nullable=True, unique=True)


class GuardPolicy(Base):
    __tablename__ = "guard_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    team_id = Column(UUID(as_uuid=True), ForeignKey("guard_teams.id"), nullable=False)
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
    team_id = Column(UUID(as_uuid=True), ForeignKey("guard_teams.id"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("guard_members.id"), nullable=True)
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
    team_id = Column(UUID(as_uuid=True), ForeignKey("guard_teams.id"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("guard_members.id"), nullable=True)
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
    team_id = Column(UUID(as_uuid=True), ForeignKey("guard_teams.id"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("guard_members.id"), nullable=True)
    monthly_limit_usd = Column(Float, nullable=False)
    alert_threshold_pct = Column(Integer, nullable=False, default=80)
    hard_limit_usd = Column(Float, nullable=True)
    default_per_developer_usd = Column(Float, nullable=True)
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
