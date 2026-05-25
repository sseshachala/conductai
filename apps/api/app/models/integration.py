import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from app.core.database import Base


class Integration(Base):
    __tablename__ = "integrations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    service = Column(String(100), nullable=False)  # github/slack/linear/digitalocean/vercel/postgres
    auth_method = Column(String(50), nullable=False)  # oauth/api_key/connection_string
    handle = Column(String(100), nullable=False)  # referenced in blocks as {{handle}}
    scopes = Column(ARRAY(String), nullable=True)
    encrypted_credentials = Column(String, nullable=True)  # AES-256-GCM encrypted blob
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    environment_id = Column(UUID(as_uuid=True), ForeignKey("environments.id"), nullable=True)

    workspace = relationship("Workspace", back_populates="integrations")
    environment = relationship("Environment", back_populates="integrations")

    __table_args__ = (
        UniqueConstraint("workspace_id", "handle", "environment_id", name="uq_integrations_workspace_handle_env"),
    )
