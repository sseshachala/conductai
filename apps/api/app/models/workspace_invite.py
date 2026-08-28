"""SQLAlchemy model for workspace_invites.

Ships to register the existing table in Base.metadata so alembic check
sees no drift. Schema mirrors 0001_baseline.py.
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class WorkspaceInvite(Base):
    __tablename__ = "workspace_invites"

    id = sa.Column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    workspace_id = sa.Column(
        UUID(as_uuid=True),
        sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    invited_email = sa.Column(sa.String(255), nullable=False)
    role = sa.Column(sa.String(50), nullable=False, server_default="developer")
    invited_by = sa.Column(sa.String(255), nullable=True)
    created_at = sa.Column(
        sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )
    accepted_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    status = sa.Column(sa.String(20), nullable=False, server_default="pending")
    expires_at = sa.Column(sa.DateTime(timezone=True), nullable=True)
    # Added by migration 0067 — Clerk org invitation tracking (used by projects.py revoke path).
    clerk_invitation_id = sa.Column(sa.Text, nullable=True)

    __table_args__ = (
        sa.UniqueConstraint("workspace_id", "invited_email", name="uq_workspace_invite_email"),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'revoked', 'expired')",
            name="ck_workspace_invites_status",
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'security', 'developer', 'viewer')",
            name="ck_workspace_invites_role",
        ),
        sa.Index("ix_workspace_invites_email", "invited_email"),
    )
