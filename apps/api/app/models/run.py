import uuid
from datetime import datetime, timezone
import sqlalchemy as sa
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


class Run(Base):
    __tablename__ = "runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_version_id = Column(UUID(as_uuid=True), ForeignKey("workflow_versions.id", ondelete="CASCADE"), nullable=False)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    triggered_by = Column(String(255), nullable=True)  # user_id / 'webhook' / 'schedule'
    status = Column(String(50), nullable=False, default="pending")  # pending/running/paused/succeeded/failed/cancelled
    started_at = Column(DateTime(timezone=True), nullable=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    current_block_id = Column(String(255), nullable=True)
    max_turns = Column(sa.Integer, nullable=True)
    state = Column(JSONB, nullable=False, default=dict)  # accumulated block outputs
    outcome = Column(JSONB, nullable=True)               # {type, artifact_url} written at run completion
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # ── Run leasing / retry tracking (migration 0024) ─────────────────────────
    attempt_count        = Column(sa.Integer, nullable=False, default=0)
    locked_at            = Column(DateTime(timezone=True), nullable=True)
    locked_by            = Column(String(255), nullable=True)
    next_retry_at        = Column(DateTime(timezone=True), nullable=True)
    last_heartbeat_time  = Column(DateTime(timezone=True), nullable=True)

    workflow_version = relationship("WorkflowVersion", back_populates="runs")
    events = relationship("RunEvent", back_populates="run", order_by="RunEvent.created_at", cascade="all, delete-orphan")


class RunEvent(Base):
    __tablename__ = "run_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    block_id = Column(String(255), nullable=True)
    kind = Column(String(100), nullable=False)  # block_started/block_completed/block_failed/approval_requested/etc
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    run = relationship("Run", back_populates="events")
