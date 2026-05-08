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
    name: str
    default_mode: str
    current_version_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime
    last_run_status: Optional[str] = None
    last_run_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class WorkflowDetailOut(WorkflowOut):
    current_version: Optional[WorkflowVersionOut] = None
