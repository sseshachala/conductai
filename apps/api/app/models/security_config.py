"""SQLAlchemy model for security_config.

Ships to register the existing table in Base.metadata so alembic check
sees no drift. Schema mirrors 0001_baseline.py.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class SecurityConfig(Base):
    __tablename__ = "security_config"

    workspace_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )
    installed = sa.Column(sa.Boolean(), nullable=False, server_default="false")
    security_emit_enabled = sa.Column(sa.Boolean(), nullable=False, server_default="true")
    security_slack_alerts_enabled = sa.Column(sa.Boolean(), nullable=False, server_default="false")
    security_slack_channel = sa.Column(sa.String(100), nullable=True)
    autopilot_enabled = sa.Column(sa.Boolean(), nullable=False, server_default="false")
    automation_workflow_on_finding = sa.Column(sa.Boolean(), nullable=False, server_default="false")
    automation_finding_severity = sa.Column(sa.String(20), nullable=False, server_default="critical")
    installed_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    created_at = sa.Column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
