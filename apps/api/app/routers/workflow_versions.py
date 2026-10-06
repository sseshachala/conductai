"""Workflow version history — read-only list + fetch for the canvas History view.

Restore is deliberately not an endpoint here: the client PUTs the old graph to
``/workflows/{id}`` so the restore runs through the same save path (trigger →
github_hook_repo sync, compiler, locking) as any other edit.
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import _assert_workspace_member, get_user_id, get_workspace_id, require_permission
from app.core.database import get_db
from app.core.workspace_context import set_workspace_rls
from app.models.workflow import Workflow, WorkflowVersion

router = APIRouter(prefix="/workflows", tags=["workflows"])


class VersionSummary(BaseModel):
    id: UUID
    created_at: datetime
    is_current: bool
    from_yaml: bool
    node_count: int
    edge_count: int
    annotation_count: int


class VersionDetail(BaseModel):
    id: UUID
    created_at: datetime
    graph: dict[str, Any]


def _workflow_in_workspace(db: Session, workflow_id: UUID, workspace_id: str, user_id: str) -> Workflow:
    if user_id and user_id != "dev":
        _assert_workspace_member(db, workspace_id, user_id)
    set_workspace_rls(db, workspace_id)
    workflow = db.query(Workflow).filter(
        Workflow.id == workflow_id,
        Workflow.workspace_id == workspace_id,
    ).first()
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow


def _jsonb_len(key: str):
    # Count server-side so listing never loads every full graph.
    return func.coalesce(func.jsonb_array_length(WorkflowVersion.graph[key]), 0)


@router.get("/{workflow_id}/versions", response_model=list[VersionSummary])
def list_versions(
    workflow_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    before: Optional[datetime] = Query(None, description="Return versions created before this timestamp (cursor)"),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _: str = Depends(require_permission("platform.workflows.view")),
):
    workflow = _workflow_in_workspace(db, workflow_id, workspace_id, user_id)
    q = db.query(
        WorkflowVersion.id,
        WorkflowVersion.created_at,
        WorkflowVersion.yaml_source.isnot(None),
        _jsonb_len("nodes"),
        _jsonb_len("edges"),
        _jsonb_len("annotations"),
    ).filter(WorkflowVersion.workflow_id == workflow.id)
    if before is not None:
        q = q.filter(WorkflowVersion.created_at < before)
    rows = q.order_by(WorkflowVersion.created_at.desc()).limit(limit).all()
    return [
        VersionSummary(
            id=vid, created_at=created_at, is_current=vid == workflow.current_version_id,
            from_yaml=bool(from_yaml), node_count=nodes, edge_count=edges, annotation_count=notes,
        )
        for vid, created_at, from_yaml, nodes, edges, notes in rows
    ]


@router.get("/{workflow_id}/versions/{version_id}", response_model=VersionDetail)
def get_version(
    workflow_id: UUID,
    version_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _: str = Depends(require_permission("platform.workflows.view")),
):
    workflow = _workflow_in_workspace(db, workflow_id, workspace_id, user_id)
    version = db.query(WorkflowVersion).filter(
        WorkflowVersion.id == version_id,
        WorkflowVersion.workflow_id == workflow.id,
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    return VersionDetail(id=version.id, created_at=version.created_at, graph=version.graph or {})
