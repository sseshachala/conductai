import uuid
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    owner_id = Column(String(255), nullable=True)
    is_approved = Column(sa.Boolean, nullable=False, default=False)
    plan = Column(String(50), nullable=False, default="free")
    kms_key_id = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = relationship("User", back_populates="workspace")
    workflows = relationship("Workflow", back_populates="workspace")
    integrations = relationship("Integration", back_populates="workspace")
