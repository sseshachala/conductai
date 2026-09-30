"""Explicit console accounts. Email and token role claims never grant membership."""
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, Column, DateTime, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ConsoleIdentityMapping(Base):
    __tablename__ = "console_identity_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    issuer = Column(String(2048), nullable=False)
    subject = Column(String(255), nullable=False)
    user_id = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(200), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("issuer", "subject", name="uq_console_issuer_subject"),)
