import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class WorkspaceInstructions(Base):
    """One row per workspace — AI rollout instructions published by an admin.
    Upsert on workspace_id (unique constraint). Version tracks publish count (v1, v2, ...).
    """

    __tablename__ = "workspace_instructions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
    )
    content = Column(Text, nullable=False, default="")
    version = Column(String(64), nullable=False, default="v1")
    updated_at = Column(DateTime(timezone=True), nullable=True)
    updated_by = Column(String(255), nullable=True)  # email of admin who published

    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_workspace_instructions_workspace"),
    )
