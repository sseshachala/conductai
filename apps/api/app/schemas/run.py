from __future__ import annotations
from typing import Any, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel


class RunCreate(BaseModel):
    triggered_by: Optional[str] = "manual"
    dry_run: bool = False
    initial_state: Optional[dict[str, Any]] = None
    max_turns: Optional[int] = None  # override default 20-turn brain budget


class RunEventOut(BaseModel):
    id: UUID
    run_id: UUID
    block_id: Optional[str] = None
    kind: str
    payload: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class RunOut(BaseModel):
    id: UUID
    workflow_version_id: UUID
    triggered_by: Optional[str] = None
    status: str
    started_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    current_block_id: Optional[str] = None
    max_turns: Optional[int] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RunDetailOut(RunOut):
    events: list[RunEventOut] = []
    state: Optional[dict[str, Any]] = None


class RunWithWorkflowOut(RunOut):
    workflow_id: str
    workflow_name: str
