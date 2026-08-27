"""SQLAlchemy model for security_policies.

Ships to register the existing table in Base.metadata so alembic check
sees no drift. Schema mirrors 0001_baseline.py.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class SecurityPolicy(Base):
    __tablename__ = "security_policies"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    workspace_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    rule_id = sa.Column(sa.String(100), nullable=False)
    description = sa.Column(sa.String(255), nullable=True)
    pattern = sa.Column(sa.String(500), nullable=True)
    finding_type = sa.Column(sa.String(50), nullable=False, server_default="other")
    severity = sa.Column(sa.String(20), nullable=False, server_default="medium")
    enabled = sa.Column(sa.Boolean(), nullable=False, server_default="true")
    builtin = sa.Column(sa.Boolean(), nullable=False, server_default="false")
    created_at = sa.Column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    updated_at = sa.Column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )

    __table_args__ = (
        sa.Index("ix_security_policies_workspace", "workspace_id"),
    )
