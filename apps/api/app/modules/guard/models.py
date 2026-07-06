import uuid
from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, func
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
    fail_mode = Column(String(20), nullable=False, default="fail_open")  # fail_open | fail_closed (CLI behavior on outage)
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
    # Dev-time persona: applies to MCP hook + daemon sync (Claude Code, Cursor, etc.).
    # 'conservative' | 'standard' | 'developer' — admin-managed; member can override.
    persona = Column(String(20), nullable=False, default="agent")
    # Runtime persona: applies to workflow execution (guard_block.py). Defaults to
    # 'conservative' so production runs always enforce the strictest rule set
    # regardless of what dev persona the workspace runs locally. Admin-only edit.
    runtime_persona = Column(String(20), nullable=False, default="conservative")
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
    intent = Column(Text, nullable=True)
    tool_sequence = Column(JSONB, nullable=True)
    session_parse_status = Column(String(20), nullable=True)  # ok|partial|failed|unsupported
    session_parser = Column(String(30), nullable=True)        # claude_code_v1|codex_v1


class GuardAuditEvent(Base):
    __tablename__ = "guard_audit_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    clerk_user_id = Column(Text, nullable=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("guard_sessions.id"), nullable=True)
    user_email = Column(String(255), nullable=True)
    ai_tool = Column(String(50), nullable=False)
    tool_call = Column(String(50), nullable=True)   # nullable: proxy rows have no tool name
    source = Column(String(20), nullable=False, default="hook")   # 'hook' | 'proxy' | 'mcp'
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
    tool_use_id = Column(String(255), nullable=True, index=True)
    hook_session_id = Column(Text, nullable=True, index=True)  # raw string session_id from hook stdin
    conductai_run_id = Column(String(255), nullable=True)
    conductai_workflow = Column(String(255), nullable=True)
    conductai_workflow_id = Column(String(255), nullable=True)
    blast_radius = Column(JSONB, nullable=True)
    ts = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    duration_ms = Column(Integer, nullable=True)
    # hash-chain integrity — do not UPDATE or DELETE rows, chain breaks
    previous_hash = Column(Text, nullable=True)
    entry_hash = Column(Text, nullable=True)


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


# ── Skill Pack Model ───────────────────────────────────────────────────────────

class SkillPack(Base):
    """Catalog of available skill packs. Rules live here, not per-workspace."""

    __tablename__ = "skill_packs"

    slug        = Column(Text, primary_key=True)            # "conduct-base", "conduct-soc2"
    version     = Column(Text, primary_key=True)            # "1.0.0"
    name        = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    tier        = Column(Text, nullable=False, default="free")  # free / paid / enterprise
    rules       = Column(JSONB, nullable=False, default=list)   # [{id, match_tool, match_pattern, ...}]
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at  = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class WorkspaceSkillPack(Base):
    """Which skill packs each workspace has installed."""

    __tablename__ = "workspace_skill_packs"

    workspace_id    = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    pack_slug       = Column(Text, primary_key=True)
    pinned_version  = Column(Text, nullable=True)   # null = always latest
    installed_by    = Column(Text, nullable=True)   # clerk_user_id
    installed_at    = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class WorkspaceCustomRule(Base):
    """Per-workspace custom guard rules. Replaces the legacy guard_policies
    table for non-pack rules. Pack rules live in skill_packs.rules JSONB."""

    __tablename__ = "workspace_custom_rules"

    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    rule_id      = Column(Text, primary_key=True)
    persona      = Column(Text, nullable=False, default="agent")  # "agent" or "proxy"
    body         = Column(JSONB, nullable=False)            # full rule shape (id, match_*, action, message, severity, ...)
    enabled      = Column(Boolean, nullable=False, default=True)
    created_by   = Column(Text, nullable=True)              # clerk_user_id
    created_at   = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))


class GuardRuleOverride(Base):
    """Per-workspace overrides on top of skill pack defaults."""

    __tablename__ = "guard_rule_overrides"

    workspace_id    = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    rule_id         = Column(Text, primary_key=True)
    action          = Column(Text, nullable=True)           # null = use pack default
    disabled        = Column(Boolean, nullable=False, default=False)
    custom_message  = Column(Text, nullable=True)
    match_pattern   = Column(Text, nullable=True)           # null = use pack default
    overridden_by   = Column(Text, nullable=True)           # clerk_user_id
    overridden_at   = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class GuardPolicyCache(Base):
    """Pre-computed flattened policy per workspace+persona. Invalidated on pack/override change."""

    __tablename__ = "guard_policy_cache"

    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    persona      = Column(Text, primary_key=True)
    payload      = Column(JSONB, nullable=False, default=list)
    version_hash = Column(Text, nullable=False)
    computed_at  = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class WorkspaceSigningKey(Base):
    """One HMAC-SHA256 signing key per workspace, used to sign GET /guard/policies/sync responses.

    The raw key_bytes are returned only at POST (generate/rotate) time. All subsequent
    reads return the fingerprint only. The CLI writes the key to ~/.conductguard/signing.key
    and verifies each fetched policy before caching it to disk.
    """

    __tablename__ = "workspace_signing_keys"

    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    key_bytes    = Column(LargeBinary(32), nullable=False)
    fingerprint  = Column(Text, nullable=False)
    created_at   = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    rotated_at   = Column(DateTime(timezone=True), nullable=True)


class DiscoveryScan(Base):
    __tablename__ = "discovery_scans"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id   = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    triggered_by   = Column(String(20), nullable=False)    # cli | schedule
    status         = Column(String(20), nullable=False)    # running | complete | failed
    agents_found   = Column(Integer, nullable=True)
    guard_coverage = Column(Integer, nullable=True)        # count under Guard
    scan_config    = Column(JSONB, nullable=True)
    started_at     = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    completed_at   = Column(DateTime(timezone=True), nullable=True)


class DiscoveredAgent(Base):
    __tablename__ = "discovered_agents"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id  = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    scan_id       = Column(UUID(as_uuid=True), ForeignKey("discovery_scans.id", ondelete="CASCADE"), nullable=True)
    name          = Column(Text, nullable=True)
    framework     = Column(String(50), nullable=True)   # langchain|crewai|autogen|claude-code|copilot|cursor|codex|windsurf
    source        = Column(String(20), nullable=True)   # config | process
    location      = Column(Text, nullable=True)         # config path | process cmd
    evidence      = Column(JSONB, nullable=True)
    risk_score    = Column(Integer, nullable=True)      # 0-100
    under_guard   = Column(Boolean, nullable=False, default=False)
    first_seen_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen_at  = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
