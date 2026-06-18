import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSON, JSONB, UUID

from app.core.database import Base


class GuardConfig(Base):
    """One Guard config per workspace — workspace IS the Guard team."""

    __tablename__ = "guard_config"

    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    invite_code = Column(Text, nullable=False)
    slug = Column(Text, nullable=True)
    alert_channel = Column(String(100), nullable=True)
    enforcement_mode = Column(String(20), nullable=False, default="warn")
    notify_on_block = Column(Boolean, nullable=False, default=True)
    notify_on_budget = Column(Boolean, nullable=False, default=True)
    resync_requested_at = Column(DateTime(timezone=True), nullable=True)
    token_guardrails = Column(JSONB, nullable=True)
    guardrail_snapshot = Column(JSONB, nullable=True)
    slack_webhook_url = Column(String(2048), nullable=True)
    slack_integration_id = Column(UUID(as_uuid=True), nullable=True)
    alert_slack_integration_id = Column(UUID(as_uuid=True), nullable=True)
    automation_security_scan = Column(Boolean, nullable=False, default=False)
    automation_workflow_trigger = Column(Boolean, nullable=False, default=False)
    # Persona governs which policy rule set applies to agents in this workspace.
    # 'conservative' | 'standard' | 'developer' — admin-managed via dashboard.
    persona = Column(String(20), nullable=False, default="standard")
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
    # NULL = inherit workspace default persona from guard_config.persona
    persona = Column(String(20), nullable=True)
    # 'user' = self-selected via conduct init; 'admin' = locked by admin
    assigned_by = Column(String(10), nullable=False, default="user")
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
    match_tokens_before_gt = Column(Integer, nullable=True)
    action = Column(String(20), nullable=False)
    message = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    builtin = Column(Boolean, nullable=False, default=False)
    pack_id = Column(String(100), nullable=True)
    # Which personas include this rule. GIN-indexed for array containment queries.
    # e.g. ['conservative','standard'] means developer persona skips this rule.
    persona_affinity = Column(ARRAY(Text), nullable=False, default=lambda: ["conservative", "standard", "developer"])
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
    archived_at = Column(DateTime(timezone=True), nullable=True)


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
    client_ip = Column(String(64), nullable=True)
    os_info = Column(String(128), nullable=True)
    hostname = Column(String(255), nullable=True)


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
    blast_radius = Column(JSONB, nullable=True)
    ts = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    duration_ms = Column(Integer, nullable=True)


class GuardSavings(Base):
    """Per-developer RTK + Agent Booster token savings snapshot, pushed by `conduct guard sync`."""

    __tablename__ = "guard_savings"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(String, nullable=False, index=True)
    member_email = Column(String, nullable=False)
    rtk_saved_tokens = Column(BigInteger, nullable=False, default=0)
    rtk_savings_pct = Column(Float, nullable=False, default=0.0)
    rtk_total_commands = Column(Integer, nullable=False, default=0)
    booster_saved_tokens = Column(BigInteger, nullable=False, default=0)
    booster_savings_pct = Column(Float, nullable=False, default=0.0)
    booster_total_reads = Column(Integer, nullable=False, default=0)
    period_start = Column(DateTime(timezone=True), nullable=True)
    period_end = Column(DateTime(timezone=True), nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GuardDeveloperTools(Base):
    """Per-developer AI tool coverage snapshot, pushed by conduct login / guard sync."""
    __tablename__ = "guard_developer_tools"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(String, nullable=False, index=True)
    user_email = Column(String, nullable=False)
    detected_tools = Column(JSON, nullable=False, default=list)   # ["claude-code", "vscode", ...]
    mcp_registered = Column(JSON, nullable=False, default=list)   # tools where conduct-mcp is wired
    hook_registered = Column(JSON, nullable=False, default=list)  # tools where Guard hook is wired
    reported_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_email", name="uq_guard_dev_tools"),
    )


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


class SessionReport(Base):
    __tablename__ = "session_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    clerk_user_id = Column(Text, nullable=True)
    developer_email = Column(String(255), nullable=False)
    archetype = Column(String(100), nullable=True)
    autonomy_score = Column(Float, nullable=True)
    planning_ratio = Column(Float, nullable=True)
    sessions = Column(Integer, nullable=False, default=0)
    prompts = Column(Integer, nullable=False, default=0)
    commits = Column(Integer, nullable=False, default=0)
    lines_per_hour = Column(Float, nullable=True)
    active_days = Column(Integer, nullable=True)
    tools_json = Column(JSONB, nullable=True)
    report_md = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
