"""
POST  /security-findings              — ingest a finding (Guard CLI or external tools)
GET   /security-findings              — list findings for workspace
GET   /security-findings/summary      — workspace-level stats
GET   /security-findings/{finding_id} — get single finding
PATCH /security-findings/{finding_id} — update status or github_issue_url
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional
from uuid import UUID

import redis
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.config import settings
from app.core.database import get_db
from app.models.security_finding import SecurityFinding

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/security-findings", tags=["security"])

QUEUE_KEY = "marshal:runs:queue"
QUEUE_MAX_DEPTH = 50_000

_VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}
_VALID_TYPES = {"injection", "path-traversal", "secret-leak", "auth-bypass", "crypto", "other"}
_VALID_STATUSES = {"open", "triaging", "fixed", "dismissed"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _redis():
    return redis.from_url(settings.redis_url, decode_responses=True)


def _enqueue_run(run_id: str) -> None:
    """Push run_id onto the Redis queue, refusing when queue is too deep."""
    r = _redis()
    depth = r.llen(QUEUE_KEY)
    if depth >= QUEUE_MAX_DEPTH:
        raise HTTPException(
            status_code=503,
            detail=f"Run queue is at capacity ({depth} pending). Try again shortly.",
        )
    r.rpush(QUEUE_KEY, run_id)


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


# ── Endpoints ─────────────────────────────────────────────────────────────────

def _ingest_finding_core(body: FindingIn, workspace_id: str, db: Session) -> SecurityFinding:
    """Write a SecurityFinding row and flush. Does NOT trigger the Redis run queue."""
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
    return finding


@router.post("", response_model=FindingOut, status_code=201)
def ingest_finding(
    body: FindingIn,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
) -> FindingOut:
    """Ingest a security finding from Guard CLI or external tools.

    If a workflow with playbook_slug='security_loop' is installed in the workspace,
    it will be triggered automatically via the Redis run queue.
    """
    finding = _ingest_finding_core(body=body, workspace_id=workspace_id, db=db)

    try:
        _trigger_security_loop(finding, workspace_id, db)
    except HTTPException:
        log.warning(
            "security_finding.queue_full",
            finding_id=str(finding.id),
            workspace_id=workspace_id,
        )
    except Exception as exc:
        log.warning(
            "security_finding.trigger_failed",
            finding_id=str(finding.id),
            workspace_id=workspace_id,
            error=str(exc),
        )

    db.commit()
    db.refresh(finding)

    # Slack alerts are handled by security_loop.yaml after triage — no pre-triage alert here.
    log.info(
        "security_finding.ingested",
        finding_id=str(finding.id),
        workspace_id=workspace_id,
        severity=finding.severity,
        tool=finding.tool,
    )
    return finding


def _send_security_slack_alert(finding: SecurityFinding, workspace_id: str, db: Session) -> None:
    """POST a Slack alert using the workspace Slack integration. Non-fatal."""
    try:
        import uuid as _uuid
        from app.models.security_config import SecurityConfig
        from app.core.crypto import decrypt
        from app.models.integration import Integration
        from app.runtime.integrations.slack import post_message

        sec = db.query(SecurityConfig).filter(
            SecurityConfig.workspace_id == _uuid.UUID(workspace_id),
        ).first()
        if not sec or not sec.installed or not sec.security_slack_alerts_enabled:
            return

        channel = sec.security_slack_channel or "general"

        query = db.query(Integration).filter(
            Integration.workspace_id == workspace_id,
            Integration.service == "slack",
            Integration.encrypted_credentials.isnot(None),
        )
        if sec.slack_integration_id:
            query = query.filter(Integration.id == sec.slack_integration_id)
        row = query.first()
        if not row:
            return
        creds = decrypt(row.encrypted_credentials)
        token = creds.get("token") or creds.get("bot_token") or ""
        if not token:
            return

        sev = finding.severity.upper()
        location = f" in {finding.file}:{finding.line}" if finding.file else ""
        developer = f" · {finding.reporter_email}" if finding.reporter_email else ""
        text = f"[{sev}] {finding.type}{location} — {finding.description} · {finding.tool}{developer}"
        post_message(token=token, channel=channel, text=text)
        log.info("security_finding.slack_sent", finding_id=str(finding.id), channel=channel)
    except Exception as exc:
        log.warning("security_finding.slack_failed", finding_id=str(finding.id), error=str(exc))


def _trigger_security_loop(finding: SecurityFinding, workspace_id: str, db: Session) -> None:
    """Look up the security_loop workflow inside the Security Automation project and enqueue a run."""
    from app.models.workflow import Workflow, WorkflowVersion
    from app.models.project import Project
    from app.models.run import Run
    from app.models.security_config import SecurityConfig
    import uuid as _uuid

    ws_uuid = _uuid.UUID(workspace_id)

    from app.routers.secure import _latest_security_automation_project
    sec_proj = _latest_security_automation_project(db, ws_uuid)
    if not sec_proj:
        return

    workflow = (
        db.query(Workflow)
        .filter(
            Workflow.workspace_id == workspace_id,
            Workflow.project_id == sec_proj.id,
            Workflow.playbook_slug == "security_loop",
        )
        .first()
    )
    if not workflow or not workflow.current_version_id:
        return

    try:
        sec_cfg = db.query(SecurityConfig).filter(SecurityConfig.workspace_id == ws_uuid).first()
        autopilot_enabled = bool(sec_cfg and sec_cfg.autopilot_enabled)
        slack_channel = (sec_cfg and sec_cfg.security_slack_channel) or "#security"
        slack_alerts_enabled = bool(sec_cfg and sec_cfg.security_slack_alerts_enabled)
    except Exception:
        autopilot_enabled = False
        slack_channel = "#security"
        slack_alerts_enabled = False

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
            "autopilot_enabled": autopilot_enabled,
            "slack_channel": slack_channel,
            "slack_alerts_enabled": slack_alerts_enabled,
        },
        "__input_contract": {
            "version": "phase2.v1",
            "status": "validated",
            "shape": "trigger",
        },
    }

    run = Run(
        workflow_version_id=workflow.current_version_id,
        triggered_by="security_finding",
        status="pending",
        state=initial_state,
    )
    db.add(run)
    db.flush()

    # Update the finding with the pipeline run_id
    finding.run_id = str(run.id)

    _enqueue_run(str(run.id))
    log.info(
        "security_finding.run_enqueued",
        finding_id=str(finding.id),
        run_id=str(run.id),
        workflow_id=str(workflow.id),
    )


@router.get("/summary", response_model=FindingSummary)
def get_summary(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
) -> FindingSummary:
    """Return workspace-level stats for the given time window."""
    cutoff = _now() - timedelta(days=days)
    base = db.query(SecurityFinding).filter(
        SecurityFinding.workspace_id == workspace_id,
        SecurityFinding.created_at >= cutoff,
    )

    total = base.count()

    by_severity: dict = {s: 0 for s in _VALID_SEVERITIES}
    for row in (
        base.with_entities(SecurityFinding.severity, func.count(SecurityFinding.id))
        .group_by(SecurityFinding.severity)
        .all()
    ):
        by_severity[row[0]] = row[1]

    by_status: dict = {s: 0 for s in _VALID_STATUSES}
    for row in (
        base.with_entities(SecurityFinding.status, func.count(SecurityFinding.id))
        .group_by(SecurityFinding.status)
        .all()
    ):
        by_status[row[0]] = row[1]

    by_tool: dict = {}
    for row in (
        base.with_entities(SecurityFinding.tool, func.count(SecurityFinding.id))
        .group_by(SecurityFinding.tool)
        .all()
    ):
        by_tool[row[0]] = row[1]

    by_type: dict = {}
    for row in (
        base.with_entities(SecurityFinding.type, func.count(SecurityFinding.id))
        .group_by(SecurityFinding.type)
        .all()
    ):
        by_type[row[0]] = row[1]

    # mttr = avg hours from created_at to updated_at for fixed findings
    mttr_hours: Optional[float] = None
    mttr_row = (
        db.query(
            func.avg(
                func.extract("epoch", SecurityFinding.updated_at)
                - func.extract("epoch", SecurityFinding.created_at)
            )
        )
        .filter(
            SecurityFinding.workspace_id == workspace_id,
            SecurityFinding.created_at >= cutoff,
            SecurityFinding.status == "fixed",
        )
        .scalar()
    )
    if mttr_row is not None:
        mttr_hours = round(float(mttr_row) / 3600, 2)

    return FindingSummary(
        total=total,
        by_severity=by_severity,
        by_status=by_status,
        by_tool=by_tool,
        by_type=by_type,
        mttr_hours=mttr_hours,
    )


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
    """List findings for the workspace, filtered by optional query params."""
    if severity and severity not in _VALID_SEVERITIES:
        raise HTTPException(
            status_code=422,
            detail=f"severity must be one of: {', '.join(sorted(_VALID_SEVERITIES))}",
        )
    if status and status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of: {', '.join(sorted(_VALID_STATUSES))}",
        )

    cutoff = _now() - timedelta(days=days)
    q = db.query(SecurityFinding).filter(
        SecurityFinding.workspace_id == workspace_id,
        SecurityFinding.created_at >= cutoff,
    )
    if severity:
        q = q.filter(SecurityFinding.severity == severity)
    if status:
        q = q.filter(SecurityFinding.status == status)
    if repo:
        q = q.filter(SecurityFinding.repo_full_name == repo)

    return (
        q.order_by(SecurityFinding.created_at.desc())
        .limit(limit)
        .all()
    )


@router.delete("", status_code=200)
def delete_findings(
    source_run_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> dict:
    """Bulk-delete findings. Scoped to workspace. source_run_id filter is required to prevent accidental full wipe."""
    if not source_run_id:
        raise HTTPException(status_code=422, detail="source_run_id filter is required")
    deleted = (
        db.query(SecurityFinding)
        .filter(
            SecurityFinding.workspace_id == workspace_id,
            SecurityFinding.source_run_id == source_run_id,
        )
        .delete()
    )
    db.commit()
    log.info("security_findings.bulk_deleted", workspace_id=workspace_id, source_run_id=source_run_id, count=deleted)
    return {"deleted": deleted}


@router.get("/{finding_id}", response_model=FindingOut)
def get_finding(
    finding_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.activity.view_all")),
) -> FindingOut:
    """Fetch a single finding by ID."""
    finding = (
        db.query(SecurityFinding)
        .filter(
            SecurityFinding.id == finding_id,
            SecurityFinding.workspace_id == workspace_id,
        )
        .first()
    )
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return finding


class TriggerFixResponse(BaseModel):
    triggered: bool
    run_id: Optional[str] = None
    reason: Optional[str] = None


@router.post("/{finding_id}/trigger-fix", response_model=TriggerFixResponse)
def trigger_fix(
    finding_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.activity.view_all")),
) -> TriggerFixResponse:
    """Trigger the security-autopilot-fix workflow for a finding.

    Looks up the finding by ID and workspace, then enqueues a run for the
    'security-autopilot-fix' playbook if it is installed in the workspace.
    Sets finding status to 'triaging' on successful enqueue.
    """
    from app.models.workflow import Workflow
    from app.models.run import Run
    from app.models.security_config import SecurityConfig

    finding = (
        db.query(SecurityFinding)
        .filter(
            SecurityFinding.id == finding_id,
            SecurityFinding.workspace_id == workspace_id,
        )
        .first()
    )
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    workflow = (
        db.query(Workflow)
        .filter(
            Workflow.workspace_id == workspace_id,
            Workflow.playbook_slug == "security-autopilot-fix",
        )
        .first()
    )
    if not workflow or not workflow.current_version_id:
        return TriggerFixResponse(
            triggered=False,
            reason="security-autopilot-fix playbook not installed",
        )

    import uuid as _uuid
    sec_cfg = db.query(SecurityConfig).filter(
        SecurityConfig.workspace_id == _uuid.UUID(workspace_id)
    ).first()
    slack_channel = (sec_cfg and sec_cfg.security_slack_channel) or "#security"

    trigger_data = {
        "finding_id": str(finding.id),
        "severity": finding.severity,
        "type": finding.type,
        "file": finding.file,
        "line": finding.line,
        "description": finding.description,
        "suggested_fix": finding.suggested_fix,
        "repo_full_name": finding.repo_full_name,
        "slack_channel": slack_channel,
    }

    initial_state = {
        "_trigger": {
            "event_type": "security_finding_fix",
            **trigger_data,
        },
        "__input_contract": {
            "version": "phase2.v1",
            "status": "validated",
            "shape": "trigger",
        },
    }

    run = Run(
        workflow_version_id=workflow.current_version_id,
        triggered_by="security_finding_fix",
        status="pending",
        state=initial_state,
    )
    db.add(run)
    db.flush()

    _enqueue_run(str(run.id))

    finding.status = "triaging"
    finding.updated_at = _now()

    db.commit()

    log.info(
        "security_finding.trigger_fix_enqueued",
        finding_id=str(finding.id),
        run_id=str(run.id),
        workflow_id=str(workflow.id),
        workspace_id=workspace_id,
    )
    return TriggerFixResponse(triggered=True, run_id=str(run.id))


@router.patch("/{finding_id}", response_model=FindingOut)
def update_finding(
    finding_id: UUID,
    body: FindingUpdate,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.edit")),
) -> FindingOut:
    """Update the status or github_issue_url of a finding."""
    finding = (
        db.query(SecurityFinding)
        .filter(
            SecurityFinding.id == finding_id,
            SecurityFinding.workspace_id == workspace_id,
        )
        .first()
    )
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    if body.status is not None:
        finding.status = body.status
    if body.github_issue_url is not None:
        finding.github_issue_url = body.github_issue_url

    finding.updated_at = _now()
    db.commit()
    db.refresh(finding)
    log.info(
        "security_finding.updated",
        finding_id=str(finding.id),
        workspace_id=workspace_id,
        status=finding.status,
    )
    return finding
