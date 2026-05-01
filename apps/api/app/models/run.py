import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


class Run(Base):
    __tablename__ = "runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_version_id = Column(UUID(as_uuid=True), ForeignKey("workflow_versions.id"), nullable=False)
    triggered_by = Column(String(255), nullable=True)  # user_id / 'webhook' / 'schedule'
    status = Column(String(50), nullable=False, default="pending")  # pending/running/paused/succeeded/failed/cancelled
    started_at = Column(DateTime(timezone=True), nullable=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    current_block_id = Column(String(255), nullable=True)
    state = Column(JSONB, nullable=False, default=dict)  # accumulated block outputs
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    workflow_version = relationship("WorkflowVersion", back_populates="runs")
    events = relationship("RunEvent", back_populates="run", order_by="RunEvent.created_at")


class RunEvent(Base):
    __tablename__ = "run_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"), nullable=False)
    block_id = Column(String(255), nullable=True)
    kind = Column(String(100), nullable=False)  # block_started/block_completed/block_failed/approval_requested/etc
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    run = relationship("Run", back_populates="events")
