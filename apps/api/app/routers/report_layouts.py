"""Workspace report layouts — CRUD for the report-builder Lens skill (#1450 PR 1).

Rows are workspace-scoped and shared across all members with view perm
(no per-user filter). Templates ("Operations" / "Observability") live in
code; "use template" writes a new row copied from the template.

layout_spec shape:
    [{"tool_name": "get_dashboard_outcomes", "hint": "kpi_card"},
     {"tool_name": "list_attention_runs",    "hint": "list"}, ...]
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.auth import get_user_id, get_workspace_id, require_permission
from app.core.database import get_db
from app.models.workspace_report_layout import WorkspaceReportLayout

router = APIRouter(prefix="/workspaces", tags=["report-layouts"])

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_VALID_HINTS = {"kpi_card", "spark", "list", "table", "agent_row"}


class WidgetSpec(BaseModel):
    tool_name: str = Field(..., min_length=1, max_length=128)
    hint: str = Field(..., min_length=1, max_length=32)


class ReportLayoutCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    layout_spec: list[WidgetSpec] = Field(default_factory=list)


class ReportLayoutUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    layout_spec: list[WidgetSpec] | None = None
    is_pinned: bool | None = None


class ReportLayoutOut(BaseModel):
    id: str
    slug: str
    name: str
    layout_spec: list[dict[str, Any]]
    is_pinned: bool = False
    created_by: str
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True)


def _validate_slug(slug: str) -> str:
    slug = slug.strip().lower()
    if not _SLUG_RE.match(slug):
        raise HTTPException(
            status_code=422,
            detail="slug must match ^[a-z0-9][a-z0-9-]{0,63}$",
        )
    return slug


def _validate_layout(spec: list[WidgetSpec]) -> list[dict[str, str]]:
    out = []
    for w in spec:
        hint = w.hint.strip()
        if hint not in _VALID_HINTS:
            raise HTTPException(
                status_code=422,
                detail=f"hint must be one of {sorted(_VALID_HINTS)}",
            )
        out.append({"tool_name": w.tool_name.strip(), "hint": hint})
    return out


def _to_out(row: WorkspaceReportLayout) -> ReportLayoutOut:
    return ReportLayoutOut(
        id=str(row.id),
        slug=row.slug,
        name=row.name,
        layout_spec=list(row.layout_spec or []),
        is_pinned=bool(getattr(row, "is_pinned", False)),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _check_ws(workspace_id: str, scoped: str) -> None:
    if str(workspace_id) != str(scoped):
        raise HTTPException(status_code=403, detail="Workspace mismatch")


@router.get(
    "/{workspace_id}/report-layouts",
    response_model=list[ReportLayoutOut],
)
def list_report_layouts(
    workspace_id: str,
    db: Session = Depends(get_db),
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.view")),
):
    _check_ws(workspace_id, scoped_ws_id)
    rows = (
        db.query(WorkspaceReportLayout)
        .filter(WorkspaceReportLayout.workspace_id == scoped_ws_id)
        .order_by(WorkspaceReportLayout.updated_at.desc())
        .all()
    )
    return [_to_out(r) for r in rows]


@router.post(
    "/{workspace_id}/report-layouts",
    response_model=ReportLayoutOut,
    status_code=201,
)
def create_report_layout(
    workspace_id: str,
    body: ReportLayoutCreate,
    db: Session = Depends(get_db),
    scoped_ws_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _: str = Depends(require_permission("platform.workflows.edit")),
):
    _check_ws(workspace_id, scoped_ws_id)
    slug = _validate_slug(body.slug)
    layout = _validate_layout(body.layout_spec)

    existing = (
        db.query(WorkspaceReportLayout)
        .filter(
            WorkspaceReportLayout.workspace_id == scoped_ws_id,
            WorkspaceReportLayout.slug == slug,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"A layout with slug '{slug}' already exists in this workspace",
        )

    now = datetime.now(timezone.utc)
    row = WorkspaceReportLayout(
        id=uuid.uuid4(),
        workspace_id=scoped_ws_id,
        slug=slug,
        name=body.name.strip(),
        layout_spec=layout,
        created_by=user_id,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.get(
    "/{workspace_id}/report-layouts/{slug}",
    response_model=ReportLayoutOut,
)
def get_report_layout(
    workspace_id: str,
    slug: str,
    db: Session = Depends(get_db),
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.view")),
):
    _check_ws(workspace_id, scoped_ws_id)
    row = (
        db.query(WorkspaceReportLayout)
        .filter(
            WorkspaceReportLayout.workspace_id == scoped_ws_id,
            WorkspaceReportLayout.slug == slug.strip().lower(),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Report layout not found")
    return _to_out(row)


@router.put(
    "/{workspace_id}/report-layouts/{slug}",
    response_model=ReportLayoutOut,
)
def update_report_layout(
    workspace_id: str,
    slug: str,
    body: ReportLayoutUpdate,
    db: Session = Depends(get_db),
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.edit")),
):
    _check_ws(workspace_id, scoped_ws_id)
    row = (
        db.query(WorkspaceReportLayout)
        .filter(
            WorkspaceReportLayout.workspace_id == scoped_ws_id,
            WorkspaceReportLayout.slug == slug.strip().lower(),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Report layout not found")

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="name cannot be empty")
        row.name = name
    if body.layout_spec is not None:
        row.layout_spec = _validate_layout(body.layout_spec)
    if body.is_pinned is not None:
        row.is_pinned = bool(body.is_pinned)

    db.commit()
    db.refresh(row)
    return _to_out(row)


@router.delete(
    "/{workspace_id}/report-layouts/{slug}",
    status_code=204,
)
def delete_report_layout(
    workspace_id: str,
    slug: str,
    db: Session = Depends(get_db),
    scoped_ws_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("platform.workflows.edit")),
):
    _check_ws(workspace_id, scoped_ws_id)
    row = (
        db.query(WorkspaceReportLayout)
        .filter(
            WorkspaceReportLayout.workspace_id == scoped_ws_id,
            WorkspaceReportLayout.slug == slug.strip().lower(),
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Report layout not found")
    db.delete(row)
    db.commit()
