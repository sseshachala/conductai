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
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, field_validator
from sqlalchemy import func, text
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
    # #1008 lineage — scanner project name (LEFT JOIN via source_project_id)
    source_project_name: Optional[str] = None

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
    # #1008 lineage — workspace's Security Automation project name (owner of the loop)
    owner_project_name: Optional[str] = None


class TriggerFixResponse(BaseModel):
    triggered: bool
    run_id: Optional[str] = None
    reason: Optional[str] = None


# ── Internal helpers ──────────────────────────────────────────────────────────

# ponytail: raw text() because security_config has no ORM model; add a model when we
# need more than 3 fields.
_SECURITY_CFG_SQL = text(
    "SELECT autopilot_enabled, security_slack_alerts_enabled, security_slack_channel "
    "FROM security_config WHERE workspace_id = :ws"
)
_SECURITY_CFG_SAFE_DEFAULTS = {
    "autopilot_enabled": False,
    "slack_alerts_enabled": False,
    "slack_channel": "",
}


def _load_security_config_defaults(db: Session, workspace_id: str) -> dict:
    """Load workspace security_config row; return safe defaults if missing.

    Playbook conditions reference these fields on ``_trigger``; without them the
    template renderer leaves ``{{...}}`` literals which crash logic-block eval
    or leak into Slack channel names. See conductai#998.
    """
    row = db.execute(_SECURITY_CFG_SQL, {"ws": workspace_id}).first()
    if row is None:
        return dict(_SECURITY_CFG_SAFE_DEFAULTS)
    return {
        "autopilot_enabled": bool(row[0]),
        "slack_alerts_enabled": bool(row[1]),
        "slack_channel": row[2] or "",
    }


def _build_finding_trigger_state(
    finding: SecurityFinding, cfg: dict, event_type: str
) -> dict:
    """Build the initial ``state`` dict for a run enqueued from a security finding.

    Shared by ``_trigger_security_loop`` (auto-triage) and ``trigger_fix``
    (autopilot fix). Both playbooks reference the same ``_trigger.*`` keys.
    """
    return {
        "_trigger": {
            "event_type": event_type,
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
            "autopilot_enabled": cfg["autopilot_enabled"],
            "slack_alerts_enabled": cfg["slack_alerts_enabled"],
            "slack_channel": cfg["slack_channel"],
        },
        "__input_contract": {"version": "phase2.v1", "status": "validated", "shape": "trigger"},
    }


# ── Security Automation project — authoritative dispatch pointer (#1005) ─────

_SECURITY_LOOP_SLUG = "security_loop"
_SECURITY_AUTOPILOT_FIX_SLUG = "security-autopilot-fix"

_ENSURE_PROJECT_SQL = text(
    "INSERT INTO projects (id, workspace_id, name, slug, project_type) "
    "VALUES (gen_random_uuid(), :ws, 'Security Automation', "
    "'security-automation', 'security_automation') "
    "ON CONFLICT (workspace_id) WHERE project_type = 'security_automation' "
    "DO NOTHING RETURNING id"
)
_LOOKUP_PROJECT_SQL = text(
    "SELECT id FROM projects "
    "WHERE workspace_id = :ws AND project_type = 'security_automation' LIMIT 1"
)
_SET_POINTER_SQL = text(
    "UPDATE workspaces SET security_automation_project_id = :pid "
    "WHERE id = :ws AND security_automation_project_id IS NULL"
)


_RESOLVE_SOURCE_PROJECT_SQL = text(
    "SELECT wf.project_id FROM runs r "
    "JOIN workflow_versions wv ON wv.id = r.workflow_version_id "
    "JOIN workflows wf ON wf.id = wv.workflow_id "
    "WHERE r.id = :run_id"
)


def _resolve_source_project_id(db: Session, source_run_id: str | None) -> str | None:
    """Resolve the scanner project that produced a finding by walking
    Run → WorkflowVersion → Workflow.project_id. Returns None when
    ``source_run_id`` is unset, invalid, or the chain has a null project_id.

    Lineage only — fix routing still uses ``repo_full_name``. See #1005.
    """
    if not source_run_id:
        return None
    try:
        row = db.execute(
            _RESOLVE_SOURCE_PROJECT_SQL, {"run_id": source_run_id}
        ).first()
    except Exception:
        return None  # invalid UUID or DB hiccup — lineage is best-effort
    if row is None or row[0] is None:
        return None
    return str(row[0])


def apply_security_install_guard(
    db: Session,
    workspace_id: str,
    template: str | None,
    body_project_id: str | None,
) -> str | None:
    """Enforce that security_loop / security-autopilot-fix installs land under
    the workspace's Security Automation project. Returns the project_id the
    caller should use, or None to pass ``body_project_id`` through unchanged.

    Raises ``HTTPException(400)`` if the caller supplied a project_id that
    isn't the Security Automation project.

    Idempotent: repeat installs get the same project id via
    ``_ensure_security_automation_project``. See conductai#1005 step 4.
    """
    if template not in (_SECURITY_LOOP_SLUG, _SECURITY_AUTOPILOT_FIX_SLUG):
        return None
    from fastapi import HTTPException as _HTTPException

    sec_project_id = _ensure_security_automation_project(db, workspace_id)
    if body_project_id and str(body_project_id) != str(sec_project_id):
        raise _HTTPException(
            status_code=400,
            detail=(
                f"{template} can only be installed under the workspace's "
                "Security Automation project. Omit project_id to auto-provision."
            ),
        )
    return sec_project_id


_OWNER_PROJECT_NAME_SQL = text(
    "SELECT p.name FROM workspaces ws "
    "LEFT JOIN projects p ON p.id = ws.security_automation_project_id "
    "WHERE ws.id = :ws"
)


def _load_owner_project_name(db: Session, workspace_id: str) -> Optional[str]:
    """Return the workspace's Security Automation project name, or None if the
    pointer isn't set (no security playbook installed). See #1008 for the
    Guard Activity lineage: Source · Owner · Target.
    """
    row = db.execute(_OWNER_PROJECT_NAME_SQL, {"ws": workspace_id}).first()
    if row is None:
        return None
    return row[0]


def _attach_source_project_name(db: Session, findings) -> None:
    """Best-effort: populate SecurityFinding.source_project_name on each row
    in-place via a single batched SELECT. Silent on any error — lineage is
    non-critical UI polish (#1008).
    """
    ids = list({f.source_project_id for f in findings if f.source_project_id})
    if not ids:
        for f in findings:
            f.source_project_name = None
        return
    try:
        from sqlalchemy import bindparam
        stmt = text("SELECT id, name FROM projects WHERE id IN :pids").bindparams(
            bindparam("pids", expanding=True)
        )
        name_by_id = {str(row[0]): row[1] for row in db.execute(stmt, {"pids": ids})}
    except Exception:
        name_by_id = {}
    for f in findings:
        f.source_project_name = name_by_id.get(str(f.source_project_id)) if f.source_project_id else None


def _ensure_security_automation_project(db: Session, workspace_id: str) -> str:
    """Get-or-create the workspace's Security Automation project and set the
    ``workspace.security_automation_project_id`` pointer if it wasn't already.

    Race-safe via the partial unique index ``projects_workspace_security_automation_uniq``
    (migration 0087). Returns the project id as a string.
    """
    row = db.execute(_ENSURE_PROJECT_SQL, {"ws": workspace_id}).first()
    if row is not None:
        project_id = str(row[0])
    else:
        project_id = str(db.execute(_LOOKUP_PROJECT_SQL, {"ws": workspace_id}).scalar())
    db.execute(_SET_POINTER_SQL, {"pid": project_id, "ws": workspace_id})
    return project_id


def _find_security_workflow(db: Session, workspace_id: str, playbook_slug: str):
    """Return the workflow for ``playbook_slug`` in this workspace, or None.

    The pointer ``workspace.security_automation_project_id`` is authoritative:
    every install of ``security_loop`` / ``security-autopilot-fix`` goes through
    ``apply_security_install_guard`` which auto-provisions the project + sets
    the pointer. Migration 0087's ``workflows_project_playbook_uniq`` partial
    index guarantees at most one workflow-per-slug under the project.

    Returns None when the workspace has no pointer (no security playbook ever
    installed) or when no matching workflow lives under the project.
    """
    from app.models.workflow import Workflow
    from app.models.workspace import Workspace

    ws = db.query(Workspace).filter(Workspace.id == workspace_id).first()
    if not ws or not ws.security_automation_project_id:
        return None
    return (
        db.query(Workflow)
        .filter(
            Workflow.project_id == ws.security_automation_project_id,
            Workflow.playbook_slug == playbook_slug,
        )
        .first()
    )


def _trigger_security_loop(finding: SecurityFinding, workspace_id: str, db: Session) -> None:
    """Find the security_loop workflow in the workspace and enqueue a run."""
    from app.models.run import Run

    workflow = _find_security_workflow(db, workspace_id, _SECURITY_LOOP_SLUG)
    if not workflow or not workflow.current_version_id:
        return

    cfg = _load_security_config_defaults(db, workspace_id)
    initial_state = _build_finding_trigger_state(finding, cfg, "security_finding")

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

@router.post("", response_model=FindingOut)
def ingest_finding(
    response: Response,
    body: FindingIn,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
) -> FindingOut:
    """Ingest a security finding. Triggers security_loop workflow if installed.

    Idempotent on (workspace_id, repo_full_name, type, file, description[:200])
    when an active finding (status in {open, triaging}) already exists — returns
    the existing row with HTTP 200 instead of creating a duplicate. Prevents
    rerun-of-scanner and rerun-of-threat-modeler from filing the same issue N
    times and cascading N duplicate security_loop runs.
    """
    now = _now()

    # Dedupe check — active findings only. Dismissed/fixed findings intentionally
    # don't dedupe: user resolved them, a new occurrence should track again.
    _desc_key = (body.description or "")[:200]
    existing = (
        db.query(SecurityFinding)
        .filter(
            SecurityFinding.workspace_id == workspace_id,
            SecurityFinding.repo_full_name == body.repo_full_name,
            SecurityFinding.type == body.type,
            SecurityFinding.file == body.file,
            func.left(SecurityFinding.description, 200) == _desc_key,
            SecurityFinding.status.in_(("open", "triaging")),
        )
        .order_by(SecurityFinding.created_at.desc())
        .first()
    )
    if existing:
        log.info("security_finding.dedupe_hit",
                 existing_id=str(existing.id), repo=body.repo_full_name,
                 type=body.type, file=body.file)
        response.status_code = 200
        return existing

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
        source_project_id=_resolve_source_project_id(db, body.source_run_id),
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

    owner_project_name = _load_owner_project_name(db, workspace_id)
    return FindingSummary(
        total=total,
        by_severity=by_severity,
        by_status=by_status,
        by_tool=by_tool,
        by_type=by_type,
        mttr_hours=mttr_hours,
        owner_project_name=owner_project_name,
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

    rows = q.order_by(SecurityFinding.created_at.desc()).limit(limit).all()
    _attach_source_project_name(db, rows)
    return rows


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
    _attach_source_project_name(db, [finding])
    return finding


@router.post("/{finding_id}/trigger-fix", response_model=TriggerFixResponse)
def trigger_fix(
    finding_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.activity.view_all")),
) -> TriggerFixResponse:
    """Trigger security-autopilot-fix for a finding. Sets status → triaging."""
    from app.models.run import Run

    finding = db.query(SecurityFinding).filter(SecurityFinding.id == finding_id, SecurityFinding.workspace_id == workspace_id).first()
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")

    workflow = _find_security_workflow(db, workspace_id, _SECURITY_AUTOPILOT_FIX_SLUG)
    if not workflow or not workflow.current_version_id:
        return TriggerFixResponse(triggered=False, reason="security-autopilot-fix playbook not installed")

    cfg = _load_security_config_defaults(db, workspace_id)
    run = Run(
        workflow_version_id=workflow.current_version_id,
        triggered_by="security_finding_fix",
        status="pending",
        state=_build_finding_trigger_state(finding, cfg, "security_finding_fix"),
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
