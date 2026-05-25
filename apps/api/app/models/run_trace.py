import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


class RunTrace(Base):
    __tablename__ = "run_traces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    block_id = Column(String(255), nullable=False)
    turn = Column(Integer, nullable=False)
    role = Column(String(50), nullable=False)   # user | assistant | tool_use | tool_result
    content = Column(Text, nullable=True)
    tool_name = Column(String(255), nullable=True)
    tool_input = Column(JSONB, nullable=True)
    tool_use_id = Column(String(255), nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    run = relationship("Run", backref="traces")
