import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class AgentMemory(Base):
    __tablename__ = "agent_memory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    playbook_slug = Column(String(100), nullable=False)
    scope = Column(String(50), nullable=False)   # repo | issue_type | agent
    key = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    embedding = Column(Text, nullable=True)      # JSON-serialised float list
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
