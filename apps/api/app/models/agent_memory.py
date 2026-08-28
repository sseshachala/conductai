import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from pgvector.sqlalchemy import Vector
from app.core.database import Base


class AgentMemory(Base):
    __tablename__ = "agent_memory"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    playbook_slug = Column(String(100), nullable=False)
    scope = Column(String(50), nullable=False)   # repo | issue_type | agent
    key = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    embedding = Column(Vector(1536), nullable=True)  # native pgvector; 1536d = OpenAI text-embedding-3-small
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_agent_memory_lookup", "workspace_id", "playbook_slug", "scope", "key"),
        Index(
            "ix_agent_memory_created",
            "workspace_id", "playbook_slug", "scope", "key", "created_at",
        ),
        Index(
            "ix_agent_memory_search",
            "workspace_id", "playbook_slug", "scope", "key",
            postgresql_where=sa.text("embedding IS NOT NULL"),
        ),
        Index(
            "ix_agent_memory_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        ),
    )
