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
    render_spec  = Column(Text, nullable=True)
    context_summary = Column(Text, nullable=True)
    # Session-scoped token — SHA-256 of the raw cond_lens_* token.
    # #1218 Step 3b — Guard-enforced Lens with per-session blast-radius.
    token_hash       = Column(String(64), nullable=True, index=True)
    token_revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at   = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))
