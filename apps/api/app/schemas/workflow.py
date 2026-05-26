from __future__ import annotations
from typing import Any, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class WorkflowGraph(BaseModel):
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []


class WorkflowCreate(BaseModel):
    name: str
    graph: WorkflowGraph = WorkflowGraph()
    template: Optional[str] = None
    repo: Optional[str] = None  # owner/repo — triggers GitHub webhook auto-registration
    project_id: Optional[UUID] = None  # project grouping within workspace
    environment_id: Optional[UUID] = None  # environment to use for this workflow
    inputs: dict[str, Any] = {}  # install-time template values e.g. {"model": "claude-haiku-..."}


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    graph: Optional[WorkflowGraph] = None


class WorkflowVersionOut(BaseModel):
    id: UUID
    workflow_id: UUID
    graph: dict[str, Any]
    compiled_artifacts: Optional[dict[str, Any]] = None
    published_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class WorkflowOut(BaseModel):
    id: UUID
    workspace_id: UUID
    project_id: Optional[UUID] = None
    name: str
    default_mode: str
    current_version_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    last_run_status: Optional[str] = None
    last_run_at: Optional[datetime] = None
    environment_id: Optional[UUID] = None
    playbook_slug: Optional[str] = None

    class Config:
        from_attributes = True


class WorkflowDetailOut(WorkflowOut):
    current_version: Optional[WorkflowVersionOut] = None
    github_hook_id: Optional[str] = None
    github_hook_repo: Optional[str] = None
    playbook_slug: Optional[str] = None
    webhook_error: Optional[str] = None  # set when webhook registration failed on install
