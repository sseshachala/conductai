import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.core.database import Base


class GlensChatSession(Base):
    __tablename__ = "glens_chat_sessions"

    id           = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    title        = Column(String, nullable=False)
    messages     = Column(Text, nullable=False, default="[]")
    context_summary = Column(Text, nullable=True)
    render_spec  = Column(Text, nullable=True)
    created_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))
