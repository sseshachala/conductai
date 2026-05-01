import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    name = Column(String(255), nullable=False)
    current_version_id = Column(UUID(as_uuid=True), ForeignKey("workflow_versions.id"), nullable=True)
    default_mode = Column(String(50), nullable=False, default="dag")  # dag/agentic
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    workspace = relationship("Workspace", back_populates="workflows")
    versions = relationship("WorkflowVersion", foreign_keys="WorkflowVersion.workflow_id", back_populates="workflow")
    current_version = relationship("WorkflowVersion", foreign_keys=[current_version_id])


class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id"), nullable=False)
    # graph stores blocks (nodes) and edges as JSONB
    # { "nodes": [...], "edges": [...] }
    graph = Column(JSONB, nullable=False, default=dict)
    # compiled_artifacts stores per-block compiled prompts and tool schemas
    # { "<block_id>": { "system_prompt": "...", "tool_schema": {...} } }
    compiled_artifacts = Column(JSONB, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)

    workflow = relationship("Workflow", foreign_keys=[workflow_id], back_populates="versions")
    runs = relationship("Run", back_populates="workflow_version")
