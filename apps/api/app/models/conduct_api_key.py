from datetime import datetime
import uuid
from sqlalchemy import Column, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class ConductApiKey(Base):
    __tablename__ = "conduct_api_keys"

    id           = Column(String(36),  primary_key=True)
    workspace_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    user_id      = Column(String(255), nullable=False)
    name         = Column(String(100), nullable=False)
    key_prefix   = Column(String(20),  nullable=False)
    key_hash     = Column(String(64),  nullable=False, unique=True)
    role         = Column(String(20),  nullable=False, default="developer")
    created_at   = Column(DateTime(timezone=True), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at   = Column(DateTime(timezone=True), nullable=True)
