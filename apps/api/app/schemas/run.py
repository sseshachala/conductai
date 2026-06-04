from __future__ import annotations
from typing import Any, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, model_validator


def _extract_repo(state: dict | None) -> str | None:
    if not state:
        return None
    trigger = state.get("_trigger") or {}
    return (trigger.get("repository") or {}).get("full_name") or None


def _extract_trigger_summary(state: dict | None) -> str | None:
    """Pull a human-readable line from the run's trigger payload."""
    if not state:
        return None
    trigger = state.get("_trigger") or {}

    # GitHub issue
    issue = trigger.get("issue") or {}
    if issue.get("title"):
        repo = trigger.get("repository", {}).get("full_name", "")
        num  = issue.get("number", "")
        title = issue["title"]
        return f"#{num} {title}" if num else title

    # GitHub / Bitbucket PR
    pr = trigger.get("pull_request") or {}
    if pr.get("title"):
        num   = pr.get("number", "")
        title = pr["title"]
        return f"PR #{num} — {title}" if num else title

    # GitLab MR
    mr = trigger.get("object_attributes") or {}
    if mr.get("title"):
        num   = mr.get("iid", "")
        title = mr["title"]
        return f"MR !{num} — {title}" if num else title

    # Dependabot / vulnerability alert
    alert = trigger.get("alert") or {}
    if alert.get("summary"):
        return alert["summary"]

    # Generic action label
    action = trigger.get("action") or trigger.get("event_type")
    if action:
        repo = (trigger.get("repository") or {}).get("full_name", "")
        return f"{repo} — {action}" if repo else action

    return None


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
    trigger_summary: Optional[str] = None
    repo: Optional[str] = None

    class Config:
        from_attributes = True

    @model_validator(mode="before")
    @classmethod
    def compute_trigger_summary(cls, data: Any) -> Any:
        if hasattr(data, "__dict__"):
            state = getattr(data, "state", None)
            data.__dict__.setdefault("trigger_summary", _extract_trigger_summary(state))
            data.__dict__.setdefault("repo", _extract_repo(state))
        elif isinstance(data, dict):
            if "trigger_summary" not in data:
                data["trigger_summary"] = _extract_trigger_summary(data.get("state"))
            if "repo" not in data:
                data["repo"] = _extract_repo(data.get("state"))
        return data


def _compute_actual_turns(state: dict | None) -> int:
    if not state:
        return 0
    return sum(
        v.get("turns", 0) or 0
        for k, v in state.items()
        if not k.startswith("__") and isinstance(v, dict)
    )


class RunDetailOut(RunOut):
    events: list[RunEventOut] = []
    state: Optional[dict[str, Any]] = None
    actual_turns: int = 0

    @model_validator(mode="before")
    @classmethod
    def compute_actual_turns(cls, data: Any) -> Any:
        if hasattr(data, "__dict__"):
            state = getattr(data, "state", None)
            data.__dict__.setdefault("actual_turns", _compute_actual_turns(state))
        elif isinstance(data, dict):
            if "actual_turns" not in data:
                data["actual_turns"] = _compute_actual_turns(data.get("state"))
        return data


class RunWithWorkflowOut(RunOut):
    workflow_id: str
    workflow_name: str
    project_id: Optional[str] = None
    project_name: Optional[str] = None
