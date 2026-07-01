from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

# ponytail: no cleanup cron yet, add if orphan tokens accumulate


class AgentRunToken(Base):
    __tablename__ = "agent_run_tokens"

    id = Column(String(36), primary_key=True)
    agent_identity_id = Column(String(36), nullable=True)
    workspace_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    run_id = Column(String(36), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False)
    token_encrypted = Column(Text, nullable=True)  # cleared after executor reads it
    created_at = Column(DateTime(timezone=True), nullable=False)
    first_used_at = Column(DateTime(timezone=True), nullable=True)
    invalidated_at = Column(DateTime(timezone=True), nullable=True)
