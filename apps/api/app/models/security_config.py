import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class SecurityConfig(Base):
    """One Security Loop config per workspace — created on module install."""

    __tablename__ = "security_config"

    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), primary_key=True)
    installed = Column(Boolean, nullable=False, default=False)
    security_emit_enabled = Column(Boolean, nullable=False, default=True)
    security_slack_alerts_enabled = Column(Boolean, nullable=False, default=False)
    security_slack_channel = Column(String(100), nullable=True)
    slack_integration_id = Column(UUID(as_uuid=True), nullable=True)
    autopilot_enabled = Column(Boolean, nullable=False, default=False)
    automation_workflow_on_finding = Column(Boolean, nullable=False, default=False)
    automation_finding_severity = Column(String(20), nullable=False, default="critical")
    installed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(DateTime(timezone=True), nullable=True)


class SecurityPolicy(Base):
    """Custom + builtin security detection policies per workspace."""

    __tablename__ = "security_policies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    rule_id = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    pattern = Column(String(500), nullable=True)
    finding_type = Column(String(50), nullable=False, default="other")
    severity = Column(String(20), nullable=False, default="medium")
    enabled = Column(Boolean, nullable=False, default=True)
    builtin = Column(Boolean, nullable=False, default=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
