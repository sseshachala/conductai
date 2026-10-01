"""Single-use, exact-action approvals for reviewed synthetic test fixtures."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class GuardFixtureApproval(Base):
    __tablename__ = "guard_fixture_approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    subject_id = Column(String(255), nullable=False)
    approved_by = Column(String(255), nullable=False)
    action_digest = Column(String(64), nullable=False)
    reason = Column(String(500), nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    consumed_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index(
            "ix_guard_fixture_approval_lookup",
            "workspace_id",
            "subject_id",
            "action_digest",
        ),
    )
