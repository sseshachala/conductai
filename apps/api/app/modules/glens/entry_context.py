"""Typed, authorized page-to-Lens handoff. URLs are references, not authority."""
from typing import Literal
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select

from app.models.run import Run, RunEvent
from app.models.workflow import Workflow, WorkflowVersion
from app.modules.agent_identity.models import AgentIdentity
from app.modules.guard.models import GuardAuditEvent
from app.modules.guard.event_access import restrict_event_query
from app.modules.glens.platform_evidence import PlatformEvidenceQuery, _member, _permission


class LensEntryContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["event", "run", "trial"]
    workspace_id: UUID
    resource_id: UUID | None = None
    block_id: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def resource_shape(self):
        if (self.kind == "trial") != (self.resource_id is None):
            raise ValueError("Event/run context requires a resource ID; trial context must not have one")
        if self.block_id is not None and self.kind != "run":
            raise ValueError("Block context requires a run")
        return self


def resolve_entry_context(db, workspace_id, user_id, context: LensEntryContext):
    ws = UUID(str(workspace_id))
    if context.workspace_id != ws:
        raise HTTPException(status_code=409, detail="Switch to the originating workspace before asking Lens.")
    if not _member(db, ws, user_id):
        raise HTTPException(status_code=403, detail="Workspace access denied")
    if context.kind == "trial":
        _permission(db, ws, user_id, "guard.activity.view_own")
        return PlatformEvidenceQuery(surface="trial")
    if context.kind == "event":
        event, identity = GuardAuditEvent, AgentIdentity
        q = db.query(event.id, event.clerk_user_id, identity.owner_user_id).outerjoin(
            identity, (event.agent_identity_id == identity.id) & (identity.workspace_id == ws),
        )
        row = restrict_event_query(q, db, ws, user_id, context.resource_id).first()
        if not row:
            raise HTTPException(status_code=404, detail="Activity is unavailable or outside your access.")
        own = row.clerk_user_id == user_id or row.owner_user_id == user_id
        return PlatformEvidenceQuery(scope="own" if own else "workspace", event_ids=[row.id], exact_resource=True)
    _permission(db, ws, user_id, "platform.runs.view")
    row = db.execute(select(Run.id, Run.triggered_by).join(
        WorkflowVersion, Run.workflow_version_id == WorkflowVersion.id,
    ).join(Workflow, WorkflowVersion.workflow_id == Workflow.id).where(
        Run.id == context.resource_id, Run.workspace_id == ws, Workflow.workspace_id == ws,
    )).first()
    if not row:
        raise HTTPException(status_code=404, detail="Run is unavailable or outside your access.")
    scope = "own" if row.triggered_by == user_id else "workspace"
    _permission(db, ws, user_id, f"guard.activity.view_{'own' if scope == 'own' else 'all'}")
    if context.block_id is not None and db.execute(select(RunEvent.id).where(
        RunEvent.run_id == row.id, RunEvent.block_id == context.block_id,
    ).limit(1)).first() is None:
        raise HTTPException(status_code=404, detail="Recorded step is unavailable.")
    return PlatformEvidenceQuery(surface="workflow", scope=scope, run_id=row.id,
                                 block_id=context.block_id, exact_resource=True)
