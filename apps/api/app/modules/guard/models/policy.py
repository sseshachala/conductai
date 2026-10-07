"""ConductGuard ORM models — skill packs, custom rules, overrides, policy cache, signing keys, discovery, verify runs, knowledge index."""

import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from app.core.database import Base


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
    precedence      = Column(Integer, nullable=False, server_default="100")  # higher wins on same-severity ties (#1737)

    __table_args__ = (
        Index("ix_workspace_skill_packs_workspace", "workspace_id"),
    )


class WorkspaceCustomRule(Base):
    """Per-workspace custom guard rules. Replaces the legacy guard_policies
    table for non-pack rules. Pack rules live in skill_packs.rules JSONB."""

    __tablename__ = "workspace_custom_rules"

    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    rule_id      = Column(Text, primary_key=True)
    persona      = Column(Text, nullable=False, default="agent")  # "agent" or "gateway" (legacy: "proxy" == "gateway")
    body         = Column(JSONB, nullable=False)            # full rule shape (id, match_*, action, message, severity, ...)
    enabled      = Column(Boolean, nullable=False, default=True)
    created_by   = Column(Text, nullable=True)              # clerk_user_id
    created_at   = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_workspace_custom_rules_workspace", "workspace_id"),
    )


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
    reason           = Column(Text, nullable=True)           # required for security-relaxing exceptions
    expires_at       = Column(DateTime(timezone=True), nullable=True)
    use_audited_at    = Column(DateTime(timezone=True), nullable=True)
    expiry_audited_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_guard_rule_overrides_workspace", "workspace_id"),
    )


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
    reads return the fingerprint only. The CLI writes the key to ~/.conduct/signing.key
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

    __table_args__ = (
        Index("ix_discovery_scans_workspace", "workspace_id"),
    )


class PolicyCertification(Base):
    __tablename__ = "policy_certifications"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id   = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    pack_slug      = Column(Text, nullable=False)
    certified_by   = Column(Text, nullable=False)   # clerk_user_id
    policy_version = Column(Text, nullable=True)    # version_hash snapshot
    certified_at   = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_policy_cert_ws_pack_ts", "workspace_id", "pack_slug", sa.text("certified_at DESC")),
    )


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
    mcp_links     = Column(JSONB, nullable=True)
    risk_score    = Column(Integer, nullable=True)      # 0-100
    under_guard   = Column(Boolean, nullable=False, default=False)
    proxy_routed  = Column(Boolean, nullable=False, default=False)
    device_id = Column(UUID(as_uuid=True), nullable=True)
    installation_id = Column(String(64), nullable=True)
    detection = Column(String(30), nullable=True)
    hook_observed_at = Column(DateTime(timezone=True), nullable=True)
    hook_event_id = Column(UUID(as_uuid=True), nullable=True)
    first_seen_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_seen_at  = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("workspace_id", "device_id", "installation_id", name="uq_discovered_agents_installation"),
        UniqueConstraint("workspace_id", "framework", "source", name="uq_discovered_agents_workspace_framework_source"),
        Index("ix_discovered_agents_workspace", "workspace_id"),
        Index("ix_discovered_agents_scan", "scan_id"),
    )


class GuardVerifyRun(Base):
    """Persisted result of a Guard Verify adversarial test battery execution."""

    __tablename__ = "guard_verify_runs"

    id           = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    score        = Column(Integer, nullable=False)
    grade        = Column(String(2), nullable=False)
    results      = Column(JSONB, nullable=False)   # list of test result dicts
    total_tests  = Column(Integer, nullable=False)
    passed_tests = Column(Integer, nullable=False)
    created_at   = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GuardKnowledgeIndex(Base):
    """Unified semantic index across Guard sources — audit events, rules, discovered agents.
    Used by GLens for intent-based search ('blocks related to secrets', etc.)."""

    __tablename__ = "guard_knowledge_index"

    id            = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id  = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    source_kind   = Column(Text, nullable=False)   # audit_event | rule | discovered_agent
    source_id     = Column(Text, nullable=False)
    canonical_text = Column(Text, nullable=False)
    meta          = Column("metadata", JSONB, nullable=False, default=dict)
    content_hash  = Column(Text, nullable=False)
    embedding     = Column(Vector(1536), nullable=True)
    source_timestamp = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    updated_at    = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint("workspace_id", "source_kind", "source_id", name="guard_knowledge_index_workspace_id_source_kind_source_id_key"),
        Index("guard_knowledge_index_workspace_id_source_kind_idx", "workspace_id", "source_kind"),
        Index("ix_guard_knowledge_index_expires_at", "expires_at"),
        Index(
            "guard_knowledge_index_embedding_idx", "embedding",
            postgresql_using="ivfflat",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"lists": "100"},
        ),
    )
