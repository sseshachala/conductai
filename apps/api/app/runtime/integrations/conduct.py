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
    """Create an incident project (or reuse existing) and enqueue a security-autopilot-fix run."""
    if db is None or not workspace_id:
        return {"skipped": True, "reason": "conduct/trigger_fix requires db and workspace_id"}
    finding_id = params.get("finding_id")
    if not finding_id:
        return {"skipped": True, "reason": "finding_id is required"}

    from app.models.security_finding import SecurityFinding
    from app.models.project import Project
    from app.models.workflow import Workflow, WorkflowVersion
    from app.models.run import Run
    from app.routers.security import _enqueue_run, _now
    from app.dsl.loader import yaml_to_graph
    from app.dsl.schema import Workflow as DSLWorkflow
    import uuid as _uuid, pathlib, yaml as _yaml

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

    # Deduplicate: reuse an existing open incident project for this finding
    incident_project = db.query(Project).filter(
        Project.workspace_id == ws_uuid,
        Project.security_finding_id == str(finding.id),
        Project.project_type == "security_incident",
    ).first()

    if not incident_project:
        label = (finding.type or "security-issue").replace("_", "-")[:40]
        project_name = f"Incident: {label}"
        incident_project = Project(
            id=_uuid.uuid4(),
            workspace_id=ws_uuid,
            name=project_name,
            slug=f"incident-{str(finding.id)[:8]}",
            project_type="security_incident",
            security_finding_id=str(finding.id),
        )
        db.add(incident_project)
        db.flush()

    # Ensure Security Autopilot Fix is installed in the incident project
    workflow = db.query(Workflow).filter(
        Workflow.workspace_id == ws_uuid,
        Workflow.project_id == incident_project.id,
        Workflow.playbook_slug == "security-autopilot-fix",
    ).first()

    if not workflow or not workflow.current_version_id:
        playbook_path = pathlib.Path(__file__).parent.parent.parent / "playbooks" / "security-autopilot-fix.yaml"
        try:
            raw = playbook_path.read_text(encoding="utf-8")
            dsl = DSLWorkflow.model_validate(_yaml.safe_load(raw))
            graph = yaml_to_graph(dsl)
        except Exception as exc:
            return {"skipped": True, "reason": f"Could not load autopilot-fix playbook: {exc}"}

        workflow = Workflow(
            id=_uuid.uuid4(),
            workspace_id=ws_uuid,
            project_id=incident_project.id,
            name="Security Autopilot Fix",
            playbook_slug="security-autopilot-fix",
        )
        db.add(workflow)
        db.flush()
        ver = WorkflowVersion(
            id=_uuid.uuid4(),
            workflow_id=workflow.id,
            graph=graph,
            compiled_artifacts={},
        )
        db.add(ver)
        db.flush()
        workflow.current_version_id = ver.id
        db.flush()

    run = Run(
        workflow_version_id=workflow.current_version_id,
        triggered_by="security_autopilot",
        status="pending",
        state={
            "_trigger": {
                "finding_id": str(finding.id),
                "incident_project_id": str(incident_project.id),
                "severity": finding.severity,
                "type": finding.type,
                "description": finding.description,
                "file": finding.file,
                "line": finding.line,
                "suggested_fix": finding.suggested_fix,
                "repo_full_name": finding.repo_full_name,
                "commit_sha": finding.commit_sha,
            }
        },
    )
    db.add(run)
    db.flush()
    finding.status = "triaging"
    _enqueue_run(str(run.id))
    db.commit()
    return {"triggered": True, "run_id": str(run.id), "finding_id": str(finding.id),
            "incident_project_id": str(incident_project.id)}
