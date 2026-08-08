from app.core.database import Base
from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID


LIFECYCLE_STATES = ("active", "pending_review", "deactivated", "expired")
RISK_TIERS = ("tier_1", "tier_2", "tier_3")


class AgentIdentity(Base):
    __tablename__ = "agent_identities"

    # --- Existing token/credential fields (unchanged) ---
    id              = Column(String(36),              primary_key=True)
    workspace_id    = Column(UUID(as_uuid=True),      nullable=False, index=True)
    name            = Column(String(100),             nullable=False)
    provider        = Column(String(50),              nullable=False, default="conduct")
    token_prefix    = Column(String(30),              nullable=False)
    token_encrypted = Column(Text,                    nullable=False)
    token_type               = Column(String(10),  nullable=False, server_default="cli")
    token_name               = Column(Text,        nullable=True)
    created_by_clerk_user_id = Column(String(100), nullable=True)
    environment_id  = Column(String(36),              nullable=True)
    created_at      = Column(DateTime(timezone=True), nullable=False)
    last_used_at    = Column(DateTime(timezone=True), nullable=True)
    expires_at               = Column(DateTime(timezone=True), nullable=True)
    refresh_token_hash       = Column(String(64),              nullable=True)
    refresh_token_expires_at = Column(DateTime(timezone=True), nullable=True)

    # --- Identity fields (added in migration 0090) ---
    source              = Column(String(50),  nullable=False, server_default="conduct", index=True)
    source_id           = Column(String(255), nullable=True)
    platform_of_origin  = Column(String(50),  nullable=False, server_default="registry", index=True)
    owner_user_id       = Column(String(100), nullable=True, index=True)
    agent_role_id       = Column(String(36),  nullable=True)
    lifecycle_state     = Column(String(20),  nullable=False, server_default="active", index=True)
    last_certified_at   = Column(DateTime(timezone=True), nullable=True)
    certification_cadence_days = Column(Integer, nullable=False, server_default="90")
    risk_tier           = Column(String(10),  nullable=False, server_default="tier_1", index=True)
    deactivated_at      = Column(DateTime(timezone=True), nullable=True)
    metadata_json       = Column(JSONB,       nullable=True)

    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN ('active', 'pending_review', 'deactivated', 'expired')",
            name="ck_agent_identities_lifecycle_state",
        ),
        CheckConstraint(
            "risk_tier IN ('tier_1', 'tier_2', 'tier_3')",
            name="ck_agent_identities_risk_tier",
        ),
        Index("ix_agent_identities_workspace_owner", "workspace_id", "owner_user_id"),
        Index(
            "ix_agent_identities_source_source_id",
            "workspace_id", "source", "source_id",
            unique=True,
            postgresql_where=text("source_id IS NOT NULL"),
        ),
    )
