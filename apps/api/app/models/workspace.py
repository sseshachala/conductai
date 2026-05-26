import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
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
    preferences = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True)

    organization = relationship("Organization", back_populates="workspaces")
    users = relationship("User", back_populates="workspace")
    members = relationship("WorkspaceUser", back_populates="workspace", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="workspace", cascade="all, delete-orphan")
    workflows = relationship("Workflow", back_populates="workspace")
    integrations = relationship("Integration", back_populates="workspace")
    environments = relationship("Environment", back_populates="workspace")
