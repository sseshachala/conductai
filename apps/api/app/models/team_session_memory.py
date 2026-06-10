import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class TeamSessionMemory(Base):
    __tablename__ = "team_session_memory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    developer_id = Column(Text, nullable=True)
    developer_email = Column(Text, nullable=True)
    session_id = Column(Text, nullable=False)
    tool = Column(String(50), nullable=False, default="claude_code")
    repo_full_name = Column(Text, nullable=True)
    topic_tags = Column(ARRAY(Text), nullable=True)
    light_summary = Column(Text, nullable=False)
    deep_summary = Column(Text, nullable=True)
    files_touched = Column(ARRAY(Text), nullable=True)
    decisions = Column(JSONB, nullable=True)
    embedding = Column(Vector(1536), nullable=True)
    confidence = Column(Float, nullable=False, default=0.5)
    visibility = Column(String(20), nullable=False, default="team")
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
