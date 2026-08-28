import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class WorkspaceUser(Base):
    __tablename__ = "workspace_users"

    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    clerk_user_id = Column(String(255), primary_key=True)
    role = Column(String(50), nullable=False, default="developer")  # admin / developer / security / viewer
    invited_by = Column(String(255), nullable=True)
    joined_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    # DB has this FK to roles.id (baseline); model was missing it (#1284).
    role_id = Column(UUID(as_uuid=True), ForeignKey("roles.id", ondelete="SET NULL"), nullable=True, index=True)

    workspace = relationship("Workspace", back_populates="members")

    __table_args__ = (
        Index("ix_workspace_users_clerk_user_id", "clerk_user_id"),
    )
