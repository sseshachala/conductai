"""
conduct — internal Conduct platform tool.

Backs the security_loop playbook's `integration: conduct` blocks. Each action
routes through the same helpers as the corresponding HTTP endpoint:

  update_finding  -> PATCH /security-findings/{id}
  trigger_fix     -> POST  /security-findings/{id}/trigger-fix

Runs inside the block executor's DB session and commits directly (matches
memory_block / guard_block / brain_block precedent).
"""
from __future__ import annotations

from datetime import datetime, timezone


TOOL_MAP: dict[str, str] = {
    "update_finding": "update_finding",
    "trigger_fix": "trigger_fix",
}


def execute(action: str, params: dict, creds: dict, db=None, workspace_id: str = "") -> dict:
    if db is None or not workspace_id:
        return {"skipped": True, "reason": "conduct integration missing db/workspace context"}
    if action == "update_finding":
        return _update_finding(db, workspace_id, params)
    if action == "trigger_fix":
        return _trigger_fix(db, workspace_id, params)
    return {"skipped": True, "reason": f"conduct action '{action}' is not implemented"}


def _update_finding(db, workspace_id: str, params: dict) -> dict:
    from app.models.security_finding import SecurityFinding
    from app.routers.security import _VALID_STATUSES

    finding_id = params.get("finding_id")
    status = params.get("status")
    if not finding_id:
        return {"skipped": True, "reason": "finding_id required"}
    if status is None or status not in _VALID_STATUSES:
        return {"skipped": True, "reason": f"invalid status '{status}'"}

    finding = (
        db.query(SecurityFinding)
        .filter(
            SecurityFinding.id == finding_id,
            SecurityFinding.workspace_id == workspace_id,
        )
        .first()
    )
    if not finding:
        return {"skipped": True, "reason": f"finding '{finding_id}' not found"}

    finding.status = status
    finding.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"updated": True, "finding_id": str(finding.id), "status": status}


def _trigger_fix(db, workspace_id: str, params: dict) -> dict:
    from app.core.queue import enqueue_run
    from app.models.run import Run
    from app.models.security_finding import SecurityFinding
    from app.routers.security import (
        _SECURITY_AUTOPILOT_FIX_SLUG,
        _build_finding_trigger_state,
        _find_security_workflow,
        _load_security_config_defaults,
    )

    finding_id = params.get("finding_id")
    if not finding_id:
        return {"skipped": True, "reason": "finding_id required"}

    finding = (
        db.query(SecurityFinding)
        .filter(
            SecurityFinding.id == finding_id,
            SecurityFinding.workspace_id == workspace_id,
        )
        .first()
    )
    if not finding:
        return {"skipped": True, "reason": f"finding '{finding_id}' not found"}

    workflow = _find_security_workflow(db, workspace_id, _SECURITY_AUTOPILOT_FIX_SLUG)
    if not workflow or not workflow.current_version_id:
        return {"skipped": True, "reason": "security_autopilot_fix playbook not installed"}

    cfg = _load_security_config_defaults(db, workspace_id)
    run = Run(
        workflow_version_id=workflow.current_version_id,
        workspace_id=workflow.workspace_id,
        triggered_by="security_finding_fix",
        status="pending",
        state=_build_finding_trigger_state(finding, cfg, "security_finding_fix"),
    )
    db.add(run)
    db.flush()
    enqueue_run(str(run.id))

    finding.status = "triaging"
    finding.updated_at = datetime.now(timezone.utc)
    db.commit()

    return {"triggered": True, "run_id": str(run.id), "finding_id": str(finding.id)}
