"""
conduct — internal Conduct platform tool.

Actions:
  emit_finding    — write a SecurityFinding directly to DB (no HTTP, no credentials needed)
  update_finding  — update status/notes on an existing SecurityFinding
"""
from __future__ import annotations

TOOL_MAP = {
    "emit_finding": "_emit_finding",
    "update_finding": "_update_finding",
    "trigger_fix": "_trigger_fix",
}


def execute(action: str, params: dict, creds: dict, db=None, workspace_id: str = "") -> dict:
    if action == "emit_finding":
        return _emit_finding(params, db=db, workspace_id=workspace_id)
    if action == "update_finding":
        return _update_finding(params, db=db, workspace_id=workspace_id)
    if action == "trigger_fix":
        return _trigger_fix(params, db=db, workspace_id=workspace_id)
    return {"skipped": True, "reason": f"Unknown conduct action: {action}"}


def _emit_finding(params: dict, db=None, workspace_id: str = "") -> dict:
    if db is None or not workspace_id:
        return {"skipped": True, "reason": "conduct/emit_finding requires db and workspace_id"}
    from app.routers.security import FindingIn, _ingest_finding_core
    body = FindingIn(
        tool=params.get("tool", "bughunter"),
        severity=params.get("severity", "medium"),
        type=params.get("type", "other"),
        description=params.get("description", ""),
        file=params.get("file") or None,
        line=int(params["line"]) if params.get("line") is not None else None,
        suggested_fix=params.get("suggested_fix") or None,
        repo_full_name=params.get("repo_full_name") or None,
        commit_sha=params.get("commit_sha") or None,
        source_run_id=params.get("source_run_id") or None,
        reporter_email=params.get("reporter_email") or None,
    )
    finding = _ingest_finding_core(body=body, workspace_id=workspace_id, db=db)
    return {"id": str(finding.id), "severity": finding.severity, "type": finding.type, "status": finding.status}


def _update_finding(params: dict, db=None, workspace_id: str = "") -> dict:
    if db is None or not workspace_id:
        return {"skipped": True, "reason": "conduct/update_finding requires db and workspace_id"}
    finding_id = params.get("finding_id")
    if not finding_id:
        return {"skipped": True, "reason": "finding_id is required"}
    from app.models.security_finding import SecurityFinding
    import uuid as _uuid
    try:
        fid = _uuid.UUID(str(finding_id))
    except ValueError:
        return {"error": f"Invalid finding_id: {finding_id}"}
    finding = db.query(SecurityFinding).filter(
        SecurityFinding.id == fid,
        SecurityFinding.workspace_id == workspace_id,
    ).first()
    if not finding:
        return {"error": f"Finding {finding_id} not found"}
    allowed = {"open", "triaging", "fixed", "dismissed"}
    new_status = params.get("status")
    if new_status and new_status in allowed:
        finding.status = new_status
    db.commit()
    return {"id": str(finding.id), "status": finding.status, "updated": True}


def _trigger_fix(params: dict, db=None, workspace_id: str = "") -> dict:
    """Enqueue a security-autopilot-fix run using the Security Automation project."""
    if db is None or not workspace_id:
        return {"skipped": True, "reason": "conduct/trigger_fix requires db and workspace_id"}
    finding_id = params.get("finding_id")
    if not finding_id:
        return {"skipped": True, "reason": "finding_id is required"}

    from app.models.security_finding import SecurityFinding
    from app.models.project import Project
    from app.models.workflow import Workflow
    from app.models.run import Run
    from app.routers.security import _enqueue_run
    import uuid as _uuid

    try:
        fid = _uuid.UUID(str(finding_id))
    except ValueError:
        return {"error": f"Invalid finding_id: {finding_id}"}

    finding = db.query(SecurityFinding).filter(
        SecurityFinding.id == fid,
        SecurityFinding.workspace_id == workspace_id,
    ).first()
    if not finding:
        return {"error": f"Finding {finding_id} not found"}

    ws_uuid = _uuid.UUID(workspace_id)

    from app.models.security_config import SecurityConfig
    sec_cfg = db.query(SecurityConfig).filter(SecurityConfig.workspace_id == ws_uuid).first()
    slack_channel = (sec_cfg and sec_cfg.security_slack_channel) or "#security"

    from app.routers.secure import _latest_security_automation_project
    sec_proj = _latest_security_automation_project(db, ws_uuid)
    if not sec_proj:
        return {"skipped": True, "reason": "Security Automation project not found — reinstall module"}

    workflow = db.query(Workflow).filter(
        Workflow.workspace_id == ws_uuid,
        Workflow.project_id == sec_proj.id,
        Workflow.playbook_slug == "security-autopilot-fix",
    ).first()
    if not workflow or not workflow.current_version_id:
        return {"skipped": True, "reason": "security-autopilot-fix not installed — enable Agentic Autopilot in settings"}

    run = Run(
        workflow_version_id=workflow.current_version_id,
        triggered_by="security_autopilot",
        status="pending",
        state={
            "_trigger": {
                "finding_id": str(finding.id),
                "severity": finding.severity,
                "type": finding.type,
                "description": finding.description,
                "file": finding.file,
                "line": finding.line,
                "suggested_fix": finding.suggested_fix,
                "repo_full_name": finding.repo_full_name,
                "commit_sha": finding.commit_sha,
                "slack_channel": slack_channel,
            }
        },
    )
    db.add(run)
    db.flush()
    finding.status = "triaging"
    _enqueue_run(str(run.id))
    db.commit()
    return {"triggered": True, "run_id": str(run.id), "finding_id": str(finding.id)}
