"""
POST  /security-findings              — ingest a finding (Guard CLI or external tools)
GET   /security-findings              — list findings for workspace
GET   /security-findings/summary      — workspace-level stats
GET   /security-findings/{finding_id} — get single finding
PATCH /security-findings/{finding_id} — update status or github_issue_url
POST  /security-findings/{finding_id}/trigger-fix — enqueue security-autopilot-fix
DELETE /security-findings             — bulk-delete by source_run_id
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.core.queue import enqueue_run
from app.models.security_finding import SecurityFinding

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/security-findings", tags=["security"])

_VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}
_VALID_TYPES = {"injection", "path-traversal", "secret-leak", "auth-bypass", "crypto", "guard_violation", "other"}
_VALID_STATUSES = {"open", "triaging", "fixed", "dismissed"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class FindingIn(BaseModel):
    tool: str
    severity: str
    type: str
    description: str
    file: Optional[str] = None
    line: Optional[int] = None
    suggested_fix: Optional[str] = None
    repo_full_name: Optional[str] = None
    commit_sha: Optional[str] = None
    source_run_id: Optional[str] = None
    reporter_email: Optional[str] = None

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        if v not in _VALID_SEVERITIES:
            raise ValueError(f"severity must be one of: {', '.join(sorted(_VALID_SEVERITIES))}")
        return v

    @field_validator("type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        if v not in _VALID_TYPES:
            raise ValueError(f"type must be one of: {', '.join(sorted(_VALID_TYPES))}")
        return v


class FindingOut(BaseModel):
    id: UUID
    workspace_id: str
    tool: str
    severity: str
    type: str
    file: Optional[str]
    line: Optional[int]
    description: str
    suggested_fix: Optional[str]
    repo_full_name: Optional[str]
    commit_sha: Optional[str]
    source_run_id: Optional[str]
    reporter_email: Optional[str]
    status: str
    github_issue_url: Optional[str]
    run_id: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}

    @field_validator("workspace_id", mode="before")
    @classmethod
    def coerce_workspace_id(cls, v):
        return str(v) if v is not None else v


class FindingUpdate(BaseModel):
    status: Optional[str] = None
    github_issue_url: Optional[str] = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in _VALID_STATUSES:
            raise ValueError(f"status must be one of: {', '.join(sorted(_VALID_STATUSES))}")
        return v


class FindingSummary(BaseModel):
    total: int
    by_severity: dict
    by_status: dict
    by_tool: dict
    by_type: dict
    mttr_hours: Optional[float]


class TriggerFixResponse(BaseModel):
    triggered: bool
    run_id: Optional[str] = None
    reason: Optional[str] = None


# ── Internal helpers ──────────────────────────────────────────────────────────

def _trigger_security_loop(finding: SecurityFinding, workspace_id: str, db: Session) -> None:
    """Find the security_loop workflow in the workspace and enqueue a run."""
    from app.models.workflow import Workflow
    from app.models.run import Run

    workflow = (
        db.query(Workflow)
        .filter(
            Workflow.workspace_id == workspace_id,
            Workflow.playbook_slug == "security_loop",
        )
        .first()
    )
    if not workflow or not workflow.current_version_id:
        return

    initial_state = {
        "_trigger": {
            "event_type": "security_finding",
            "finding_id": str(finding.id),
            "tool": finding.tool,
            "severity": finding.severity,
            "type": finding.type,
            "description": finding.description,
            "file": finding.file,
            "line": finding.line,
            "suggested_fix": finding.suggested_fix,
            "repo_full_name": finding.repo_full_name,
            "commit_sha": finding.commit_sha,
            "source_run_id": finding.source_run_id,
        },
        "__input_contract": {"version": "phase2.v1", "status": "validated", "shape": "trigger"},
    }

    run = Run(
        workflow_version_id=workflow.current_version_id,
        workspace_id=workflow.workspace_id,
        triggered_by="security_finding",
        status="pending",
        state=initial_state,
    )
    db.add(run)
    db.flush()
    finding.run_id = str(run.id)
    enqueue_run(str(run.id))
    log.info("security_finding.run_enqueued", finding_id=str(finding.id), run_id=str(run.id))


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", response_model=FindingOut, status_code=201)
def ingest_finding(
    body: FindingIn,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
) -> FindingOut:
    """Ingest a security finding. Triggers security_loop workflow if installed."""
    now = _now()
    finding = SecurityFinding(
        id=uuid.uuid4(),
        workspace_id=workspace_id,
        tool=body.tool,
        severity=body.severity,
        type=body.type,
        file=body.file,
        line=body.line,
        description=body.description,
        suggested_fix=body.suggested_fix,
        repo_full_name=body.repo_full_name,
        commit_sha=body.commit_sha,
        source_run_id=body.source_run_id,
        reporter_email=body.reporter_email,
        status="open",
        created_at=now,
        updated_at=now,
    )
    db.add(finding)
    db.flush()

    try:
        _trigger_security_loop(finding, workspace_id, db)
    except HTTPException:
        log.warning("security_finding.queue_full", finding_id=str(finding.id))
    except Exception as exc:
        log.warning("security_finding.trigger_failed", finding_id=str(finding.id), error=str(exc))

    db.commit()
    db.refresh(finding)
    log.info("security_finding.ingested", finding_id=str(finding.id), severity=finding.severity, tool=finding.tool)
    return finding


@router.get("/summary", response_model=FindingSummary)
def get_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
) -> FindingSummary:
    cutoff = _now() - timedelta(days=days)
    base = db.query(SecurityFinding).filter(
        SecurityFinding.workspace_id == workspace_id,
        SecurityFinding.created_at >= cutoff,
    )

    total = base.count()

    by_severity: dict = {s: 0 for s in _VALID_SEVERITIES}
    for row in base.with_entities(SecurityFinding.severity, func.count(SecurityFinding.id)).group_by(SecurityFinding.severity).all():
        by_severity[row[0]] = row[1]

    by_status: dict = {s: 0 for s in _VALID_STATUSES}
    for row in base.with_entities(SecurityFinding.status, func.count(SecurityFinding.id)).group_by(SecurityFinding.status).all():
        by_status[row[0]] = row[1]

    by_tool: dict = {}
    for row in base.with_entities(SecurityFinding.tool, func.count(SecurityFinding.id)).group_by(SecurityFinding.tool).all():
        by_tool[row[0]] = row[1]

    by_type: dict = {}
    for row in base.with_entities(SecurityFinding.type, func.count(SecurityFinding.id)).group_by(SecurityFinding.type).all():
        by_type[row[0]] = row[1]

    mttr_hours: Optional[float] = None
    mttr_row = (
        db.query(func.avg(func.extract("epoch", SecurityFinding.updated_at) - func.extract("epoch", SecurityFinding.created_at)))
        .filter(SecurityFinding.workspace_id == workspace_id, SecurityFinding.created_at >= cutoff, SecurityFinding.status == "fixed")
        .scalar()
    )
    if mttr_row is not None:
        mttr_hours = round(float(mttr_row) / 3600, 2)

    return FindingSummary(total=total, by_severity=by_severity, by_status=by_status, by_tool=by_tool, by_type=by_type, mttr_hours=mttr_hours)


@router.get("", response_model=list[FindingOut])
def list_findings(
    severity: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    repo: Optional[str] = Query(default=None),
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.activity.view_all")),
) -> list[FindingOut]:
    if severity and severity not in _VALID_SEVERITIES:
        raise HTTPException(status_code=422, detail=f"severity must be one of: {', '.join(sorted(_VALID_SEVERITIES))}")
    if status and status not in _VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of: {', '.join(sorted(_VALID_STATUSES))}")

    cutoff = _now() - timedelta(days=days)
    q = db.query(SecurityFinding).filter(SecurityFinding.workspace_id == workspace_id, SecurityFinding.created_at >= cutoff)
    if severity:
        q = q.filter(SecurityFinding.severity == severity)
    if status:
        q = q.filter(SecurityFinding.status == status)
    if repo:
        q = q.filter(SecurityFinding.repo_full_name == repo)

    return q.order_by(SecurityFinding.created_at.desc()).limit(limit).all()


@router.delete("", status_code=200)
def delete_findings(
    source_run_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> dict:
    if not source_run_id:
        raise HTTPException(status_code=422, detail="source_run_id filter is required")
    deleted = (
        db.query(SecurityFinding)
        .filter(SecurityFinding.workspace_id == workspace_id, SecurityFinding.source_run_id == source_run_id)
        .delete()
    )
    db.commit()
    return {"deleted": deleted}


@router.get("/{finding_id}", response_model=FindingOut)
def get_finding(
    finding_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.activity.view_all")),
) -> FindingOut:
    finding = db.query(SecurityFinding).filter(SecurityFinding.id == finding_id, SecurityFinding.workspace_id == workspace_id).first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


@router.post("/{finding_id}/trigger-fix", response_model=TriggerFixResponse)
def trigger_fix(
    finding_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.activity.view_all")),
) -> TriggerFixResponse:
    """Trigger security-autopilot-fix for a finding. Sets status → triaging."""
    from app.models.workflow import Workflow
    from app.models.run import Run

    finding = db.query(SecurityFinding).filter(SecurityFinding.id == finding_id, SecurityFinding.workspace_id == workspace_id).first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    workflow = db.query(Workflow).filter(Workflow.workspace_id == workspace_id, Workflow.playbook_slug == "security_autopilot_fix").first()
    if not workflow or not workflow.current_version_id:
        return TriggerFixResponse(triggered=False, reason="security_autopilot_fix playbook not installed")

    run = Run(
        workflow_version_id=workflow.current_version_id,
        triggered_by="security_finding_fix",
        status="pending",
        state={
            "_trigger": {
                "event_type": "security_finding_fix",
                "finding_id": str(finding.id),
                "severity": finding.severity,
                "type": finding.type,
                "file": finding.file,
                "line": finding.line,
                "description": finding.description,
                "suggested_fix": finding.suggested_fix,
                "repo_full_name": finding.repo_full_name,
            },
            "__input_contract": {"version": "phase2.v1", "status": "validated", "shape": "trigger"},
        },
    )
    db.add(run)
    db.flush()
    enqueue_run(str(run.id))

    finding.status = "triaging"
    finding.updated_at = _now()
    db.commit()

    log.info("security_finding.trigger_fix_enqueued", finding_id=str(finding.id), run_id=str(run.id))
    return TriggerFixResponse(triggered=True, run_id=str(run.id))


@router.patch("/{finding_id}", response_model=FindingOut)
def update_finding(
    finding_id: UUID,
    body: FindingUpdate,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.edit")),
) -> FindingOut:
    finding = db.query(SecurityFinding).filter(SecurityFinding.id == finding_id, SecurityFinding.workspace_id == workspace_id).first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if body.status is not None:
        finding.status = body.status
    if body.github_issue_url is not None:
        finding.github_issue_url = body.github_issue_url

    finding.updated_at = _now()
    db.commit()
    db.refresh(finding)
    return finding
