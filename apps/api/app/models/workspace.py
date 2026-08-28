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
    # Added by revision 0066 — model was missing it (#1284).
    # Partial unique index (see __table_args__): one Clerk org ↔ one workspace,
    # NULLs allowed for workspaces not yet linked to Clerk.
    clerk_org_id = sa.Column(sa.Text(), nullable=True)

    # Authoritative pointer to the Security Automation project for this workspace.
    # See conductai#1005 — replaces .first() dispatch roulette for security_loop /
    # security-autopilot-fix.
    security_automation_project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        sa.Index(
            "ix_workspaces_clerk_org_id",
            "clerk_org_id",
            unique=True,
            postgresql_where=sa.text("clerk_org_id IS NOT NULL"),
        ),
    )

    organization = relationship("Organization", back_populates="workspaces")
    users = relationship("User", back_populates="workspace")
    members = relationship("WorkspaceUser", back_populates="workspace", cascade="all, delete-orphan")
    projects = relationship(
        "Project",
        back_populates="workspace",
        cascade="all, delete-orphan",
        foreign_keys="Project.workspace_id",
    )
    workflows = relationship("Workflow", back_populates="workspace")
    integrations = relationship("Integration", back_populates="workspace")
    environments = relationship("Environment", back_populates="workspace")
