"""Serialise AgentRunToken rows with their workflow name in one query."""
import uuid

from sqlalchemy.orm import Session

from app.models.run import Run
from app.models.workflow import Workflow, WorkflowVersion


def _norm(run_id) -> str:
    try:
        return str(uuid.UUID(str(run_id)))
    except ValueError:
        return ""


def serialize_run_tokens(db: Session, rows: list) -> list[dict]:
    """Batch Run -> WorkflowVersion -> Workflow lookup (was up to 3 queries per row)."""
    run_ids = {uuid.UUID(k) for k in (_norm(r.run_id) for r in rows) if k}
    wf_by_run: dict[str, tuple[str, str]] = {}
    if run_ids:
        for run_id, wf_id, wf_name in (
            db.query(Run.id, Workflow.id, Workflow.name)
            .join(WorkflowVersion, WorkflowVersion.id == Run.workflow_version_id)
            .join(Workflow, Workflow.id == WorkflowVersion.workflow_id)
            .filter(Run.id.in_(run_ids))
            .all()
        ):
            wf_by_run[str(run_id)] = (str(wf_id), wf_name)

    result = []
    for r in rows:
        workflow_id, workflow_name = wf_by_run.get(_norm(r.run_id), (None, None))
        result.append({
            "id": r.id,
            "run_id": r.run_id,
            "token_prefix": r.token_prefix,
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "first_used_at": r.first_used_at.isoformat() if r.first_used_at else None,
            "invalidated_at": r.invalidated_at.isoformat() if r.invalidated_at else None,
        })
    return result
