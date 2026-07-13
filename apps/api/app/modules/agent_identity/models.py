from app.core.database import Base
from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID


class AgentIdentity(Base):
    __tablename__ = "agent_identities"

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
