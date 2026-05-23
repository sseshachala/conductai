import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class WorkspaceUser(Base):
    __tablename__ = "workspace_users"

    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    clerk_user_id = Column(String(255), primary_key=True)
    role = Column(String(50), nullable=False, default="editor")  # admin / editor / viewer
    invited_by = Column(String(255), nullable=True)
    joined_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    workspace = relationship("Workspace", back_populates="members")
