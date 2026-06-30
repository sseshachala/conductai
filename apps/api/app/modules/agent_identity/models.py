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
    environment_id  = Column(String(36),              nullable=True)
    created_at      = Column(DateTime(timezone=True), nullable=False)
    last_used_at    = Column(DateTime(timezone=True), nullable=True)
