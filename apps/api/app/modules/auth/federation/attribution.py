"""Safe historical attribution for existing authorized Flight Recorder/Lens reads."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, ValidationError

from app.models.run import Run, RunEvent


class FederationAttribution(BaseModel):
    model_config = ConfigDict(extra="ignore")
    schema_version: int
    request_id: UUID
    caller_id: UUID
    principal_id: UUID
    grant_id: UUID
    connection_id: UUID
    mapping_version: str
    evidence_expires_at: datetime


def attribution(metadata):
    if not isinstance(metadata, dict) or not isinstance(metadata.get("federation"), dict):
        return None
    try:
        return FederationAttribution.model_validate(metadata["federation"]).model_dump(mode="json")
    except (ValidationError, TypeError, ValueError):
        return None


def run_attribution(db, workspace_id, run_id):
    from .workflow import EVENT_KIND
    row = db.query(RunEvent).join(Run, Run.id == RunEvent.run_id).filter(
        Run.workspace_id == workspace_id, Run.id == run_id, RunEvent.kind == EVENT_KIND,
    ).first()
    return attribution({"federation": row.payload}) if row else None
