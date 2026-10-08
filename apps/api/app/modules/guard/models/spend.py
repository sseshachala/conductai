"""ConductGuard ORM models — savings, developer tools, spend budgets, reservations, rate limits, session reports."""

import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.core.database import Base


class GuardSavings(Base):
    """Per-developer RTK + Agent Booster token savings snapshot, pushed by `conduct guard sync`."""

    __tablename__ = "guard_savings"

    id = Column(Integer, primary_key=True)
    workspace_id = Column(Text, nullable=False, index=True)
    member_email = Column(Text, nullable=False)
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
    workspace_id = Column(Text, nullable=False, index=True)
    user_email = Column(Text, nullable=False)
    detected_tools = Column(JSONB, nullable=False, default=list)   # ["claude-code", "vscode", ...]
    mcp_registered = Column(JSONB, nullable=False, default=list)   # tools where conduct-mcp is wired
    hook_registered = Column(JSONB, nullable=False, default=list)  # tools where Guard hook is wired
    reported_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("workspace_id", "user_email", name="uq_guard_dev_tools"),
    )


class GuardSpendBudget(Base):
    __tablename__ = "guard_spend_budgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    clerk_user_id = Column(Text, nullable=True)
    ai_tool = Column(Text, nullable=True)
    # Added by revision 0140 — per-agent scope alongside per-user (clerk_user_id)
    # and per-tool (ai_tool). ondelete=SET NULL so budget rows survive identity
    # deletion but decay to workspace-scoped meaning.
    agent_identity_id = Column(
        String(36),
        ForeignKey("agent_identities.id", ondelete="CASCADE", name="fk_guard_spend_budgets_agent_identity"),
        nullable=True,
    )
    monthly_limit_usd = Column(Float, nullable=False)
    alert_threshold_pct = Column(Integer, nullable=False, default=80)
    hard_limit_usd = Column(Float, nullable=True)
    hard_cap_enabled = Column(Boolean, nullable=False, server_default=sa.text("false"), default=False)
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

    __table_args__ = (
        Index(
            "uq_guard_spend_workspace_default",
            "workspace_id",
            sa.text("COALESCE(agent_identity_id, '')"),
            sa.text("COALESCE(ai_tool, '')"),
            unique=True,
            postgresql_where=sa.text("clerk_user_id IS NULL"),
        ),
        Index(
            "uq_guard_spend_workspace_member",
            "workspace_id",
            "clerk_user_id",
            sa.text("COALESCE(agent_identity_id, '')"),
            sa.text("COALESCE(ai_tool, '')"),
            unique=True,
            postgresql_where=sa.text("clerk_user_id IS NOT NULL"),
        ),
        Index(
            "ix_guard_spend_budgets_ws_agent",
            "workspace_id",
            "agent_identity_id",
        ),
    )


class BudgetReservation(Base):
    """Durable acceptance log for the atomic reservation ledger (PR 6d).

    Every accepted reserve() writes a row before the Redis counter is
    touched. On Redis cold start the reconciler replays open rows so a
    Redis flush cannot silently restore capacity mid-request.
    """
    __tablename__ = "budget_reservations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    ai_tool = Column(Text, nullable=True)
    period_key = Column(Text, nullable=False)
    # Added by revision 0142 (R1 fix) — clerk_user_id was already part of
    # the Redis key scope (Fix 1 P1 #1) but the durable column was
    # missing. Nullable so pre-0142 rows stay valid; NULL = workspace-wide.
    clerk_user_id = Column(Text, nullable=True)
    # Added by revision 0140 — multi-scope columns for the all-permit
    # reservation contract. All nullable so pre-0140 single-scope callers keep
    # working; the ledger-wiring PR starts populating them from request context.
    agent_identity_id = Column(
        String(36),
        ForeignKey("agent_identities.id", ondelete="SET NULL", name="fk_budget_reservations_agent_identity"),
        nullable=True,
    )
    # R13 (reviewer P2): tombstone captures the agent's original id
    # before the FK nulls the primary column. Populated by a future
    # BEFORE DELETE trigger or app-level cleanup — this migration
    # only adds the schema slot.
    deleted_agent_identity_id = Column(String(36), nullable=True)
    source = Column(Text, nullable=True)         # transport: 'gateway' | 'mcp' | 'workflow'
    client_tool = Column(Text, nullable=True)    # client-declared tool string
    request_id = Column(UUID(as_uuid=True), nullable=True)  # correlates to GuardAuditEvent.request_id
    estimated_cents = Column(Integer, nullable=False)
    actual_cents = Column(Integer, nullable=True)
    # R9 (reviewer P1): microdollar precision. 1 cent = 10 000 micros.
    # Nullable so cents-mode callers continue to work; new writers
    # populate both for a clean deprecation of the cents columns.
    estimated_micros = Column(sa.BigInteger, nullable=True)
    actual_micros = Column(sa.BigInteger, nullable=True)
    status = Column(Text, nullable=False, server_default=sa.text("'open'"), default="open")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=sa.func.now(),
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "ix_budget_reservations_open",
            "workspace_id",
            "period_key",
            postgresql_where=sa.text("status = 'open'"),
        ),
        Index("ix_budget_reservations_created_at", "created_at"),
        Index(
            "ix_budget_reservations_scope",
            "workspace_id",
            "agent_identity_id",
            "period_key",
        ),
        Index("ix_budget_reservations_request_id", "request_id"),
        Index(
            "ix_budget_reservations_scope_user",
            "workspace_id",
            "clerk_user_id",
            "period_key",
        ),
        # R13: historical lookup by tombstoned agent.
        Index(
            "ix_budget_reservations_deleted_agent",
            "workspace_id",
            "deleted_agent_identity_id",
        ),
    )


class GuardRateLimit(Base):
    """Per-workspace / per-agent-identity RPM+TPM caps (#980).

    workspace_id + agent_identity_id=NULL row = workspace default.
    workspace_id + agent_identity_id=X row  = override for that agent identity.
    Enforced by app.modules.guard.rate_limit.check_rate_limit at proxy step 4d.2.
    """
    __tablename__ = "guard_rate_limits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    agent_identity_id = Column(String(36), ForeignKey("agent_identities.id", ondelete="CASCADE"), nullable=True)
    rpm = Column(Integer, nullable=True)
    tpm = Column(Integer, nullable=True)
    created_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "agent_identity_id", name="uq_guard_rate_limits_scope"),
        Index("idx_guard_rate_limits_ws", "workspace_id"),
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
    embedding = Column(Vector(1536), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_session_reports_workspace", "workspace_id"),
        Index("ix_session_reports_email", "developer_email"),
        Index("ix_session_reports_ws_created", "workspace_id", "created_at"),
    )
