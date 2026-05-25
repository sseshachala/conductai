import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(String(255), nullable=False)
    actor_id = Column(String(255), nullable=True)    # Clerk user_id
    actor_email = Column(String(255), nullable=True)
    actor_role = Column(String(50), nullable=True)
    action = Column(String(100), nullable=False)     # credential.added, run.triggered, etc.
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(255), nullable=True)
    meta = Column("metadata", JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
