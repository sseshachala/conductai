"""Additive connection storage; no federation authentication is activated here."""
from uuid import uuid4
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.core.database import Base


class FederationConnection(Base):
    __tablename__ = "federation_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False, index=True)
    integration_id = Column(UUID(as_uuid=True), nullable=False)
    authentication_mode = Column(String(32), nullable=False, default="delegated", server_default="delegated")
    revision = Column(Integer, nullable=False, default=1)
    config = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("integration_id", "authentication_mode", name="uq_federation_integration_mode"),
        CheckConstraint("authentication_mode IN ('delegated', 'okta_agent')", name="ck_federation_authentication_mode"),
        UniqueConstraint("workspace_id", "id", name="uq_federation_workspace_id"),
        ForeignKeyConstraint(["workspace_id", "integration_id"], ["integrations.workspace_id", "integrations.id"],
                             name="fk_federation_integration_workspace"),
        CheckConstraint("revision > 0", name="ck_federation_revision"),
    )
