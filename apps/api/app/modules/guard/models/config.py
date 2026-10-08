"""ConductGuard ORM models — workspace/member config, sessions, notification channels."""

import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.core.database import Base


class GuardConfig(Base):
    """One Guard config per workspace — workspace IS the Guard team."""

    __tablename__ = "guard_config"

    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    invite_code = Column(Text, nullable=False)
    slug = Column(Text, nullable=True)
    alert_channel = Column(Text, nullable=True)
    enforcement_mode = Column(String(20), nullable=False, default="warn")
    fail_mode = Column(String(20), nullable=False, default="fail_closed")  # fail_open | fail_closed (CLI behavior on outage)
    notify_on_block = Column(Boolean, nullable=False, default=True)
    notify_on_budget = Column(Boolean, nullable=False, default=True)
    resync_requested_at = Column(DateTime(timezone=True), nullable=True)
    token_guardrails = Column(JSONB, nullable=True)
    guardrail_snapshot = Column(JSONB, nullable=True)
    alert_slack_integration_id = Column(UUID(as_uuid=True), nullable=True)
    automation_security_scan = Column(Boolean, nullable=False, default=False)
    automation_workflow_trigger = Column(Boolean, nullable=False, default=False)
    # Dev-time persona: applies to MCP hook + daemon sync (Claude Code, Cursor, etc.).
    # 'conservative' | 'standard' | 'developer' — admin-managed; member can override.
    persona = Column(String(20), nullable=False, default="agent")
    # Runtime persona: applies to workflow execution (guard_block.py). Defaults to
    # 'conservative' so production runs always enforce the strictest rule set
    # regardless of what dev persona the workspace runs locally. Admin-only edit.
    runtime_persona = Column(String(20), nullable=False, default="agent")
    deny_on_error = Column(Boolean, nullable=False, default=True)  # fail-closed on policy eval error
    notify_on_fail_open = Column(Boolean, nullable=False, default=True)  # customer-facing WARNING when Guard engine falls open (#1520)
    advisory_mode = Column(Boolean, nullable=False, default=False)  # log all, block nothing
    # Days to keep a Guard Inbox row open before the auto-close worker flips
    # it to resolved:auto. 0 = never auto-close (opt-out). Default 30 matches
    # the migration 0123 initial backfill window.
    inbox_auto_close_days = Column(
        Integer, nullable=False, default=30, server_default=sa.text("30")
    )
    arg_anomaly_enabled = Column(Boolean, nullable=False, default=False)  # record-only arg-drift observation, advisory audit events only
    # Tunables for the record-only checkpoint, so thresholds move by config
    # PATCH instead of a deploy. NULL = use the module default in
    # app.modules.behavior.arg_anomaly, keeping the default in one place.
    arg_anomaly_zscore_threshold = Column(Float, nullable=True)
    arg_anomaly_min_samples = Column(Integer, nullable=True)
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
    # Version string of workspace_instructions last synced by this member's CLI.
    # Null = never synced. Written by conduct guard sync.
    instructions_version = Column(String(64), nullable=True)
    joined_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    # Added by revision 0062 — model was missing this FK (#1284).
    agent_identity_id = Column(
        String(36),
        ForeignKey("agent_identities.id", ondelete="SET NULL", name="fk_guard_member_config_agent_identity"),
        nullable=True,
        index=True,
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

    __table_args__ = (
        Index("ix_guard_sessions_ws_started", "workspace_id", sa.text("started_at DESC NULLS LAST")),
    )


class GuardNotificationChannel(Base):
    """Per-action notification routing (#1142 Phase 1).

    One row per (workspace, action, channel_type, channel_ref). Phase 1 supports
    channel_type='slack'; Phase 2 adds email/pagerduty/webhook.

    Legacy guard_config.alert_channel + notify_on_block/notify_on_budget stay in
    place; the router auto-seeds this table from them on first read.
    """

    __tablename__ = "guard_notification_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    action = Column(String(20), nullable=False)  # block | warn | audit | approval
    channel_type = Column(String(20), nullable=False, default="slack")
    integration_id = Column(UUID(as_uuid=True), nullable=True)
    channel_ref = Column(String(200), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    dedupe_window_sec = Column(Integer, nullable=False, default=300)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_guard_notif_workspace_action", "workspace_id", "action"),
        Index("idx_guard_notif_workspace_enabled", "workspace_id", "enabled"),
    )
