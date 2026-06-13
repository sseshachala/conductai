import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


from sqlalchemy import Text


class Workflow(Base):
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id"), nullable=False)
    name = Column(String(255), nullable=False)
    current_version_id = Column(UUID(as_uuid=True), ForeignKey("workflow_versions.id", ondelete="SET NULL"), nullable=True)
    default_mode = Column(String(50), nullable=False, default="dag")  # dag/agentic

    # Optional link to a YAML file in a customer's GitHub repo. When both are
    # set, the runtime can (phase 2) re-fetch the YAML at run time so a
    # ``delegator.yml`` committed in the customer's repo becomes the source
    # of truth instead of the DB copy.
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    source_repo = Column(String(255), nullable=True)
    source_path = Column(String(512), nullable=True)
    environment_id = Column(UUID(as_uuid=True), ForeignKey("environments.id"), nullable=True)

    # Auto-registered GitHub webhook — stored so we can deregister on delete
    github_hook_id = Column(String(255), nullable=True)
    github_hook_repo = Column(String(255), nullable=True)  # owner/repo format
    github_hook_label = Column(String(255), nullable=True)  # label filter this workflow watches
    playbook_slug = Column(String(100), nullable=True)
    default_max_turns = Column(Integer(), nullable=True)
    is_template = Column(Boolean(), nullable=False, default=False, server_default="false")
    source = Column(String(32), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    archived_at = Column(DateTime(timezone=True), nullable=True)

    project = relationship("Project", back_populates="workflows")
    workspace = relationship("Workspace", back_populates="workflows")
    environment = relationship("Environment")
    versions = relationship("WorkflowVersion", foreign_keys="WorkflowVersion.workflow_id", back_populates="workflow", cascade="all, delete-orphan")
    current_version = relationship("WorkflowVersion", foreign_keys=[current_version_id])


class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id", ondelete="CASCADE"), nullable=False)

    # yaml_source is the canonical workflow definition; ``graph`` below is a
    # cached projection produced by app.dsl.loader.yaml_to_graph. New writes
    # should always populate yaml_source; ``graph`` is regenerated from it.
    yaml_source = Column(Text, nullable=True)

    # graph stores blocks (nodes) and edges as JSONB — derived from yaml_source.
    # { "nodes": [...], "edges": [...] }
    graph = Column(JSONB, nullable=False, default=dict)
    # compiled_artifacts stores per-block compiled prompts and tool schemas
    # { "<block_id>": { "system_prompt": "...", "tool_schema": {...} } }
    compiled_artifacts = Column(JSONB, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    workflow = relationship("Workflow", foreign_keys=[workflow_id], back_populates="versions")
    runs = relationship("Run", back_populates="workflow_version", cascade="all, delete-orphan")
