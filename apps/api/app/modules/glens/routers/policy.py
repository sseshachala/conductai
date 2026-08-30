"""Policy apply endpoint — create / patch / delete workspace custom rules.

Split out of chat.py in #1459.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.guard.models import WorkspaceCustomRule

from ._helpers import _parse_workspace_id

router = APIRouter(prefix="/glens", tags=["glens"])


class PolicyApplyRequest(BaseModel):
    action: str
    draft: dict
    target_rule_id: str | None = None


@router.post("/policy/apply", status_code=201)
def policy_apply(
    req: PolicyApplyRequest,
    _: str = Depends(require_permission("guard.policies.edit")),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
):
    ws_uuid = _parse_workspace_id(workspace_id)

    if req.action == "create":
        rule_id = req.draft.get("rule_id")
        if not rule_id:
            raise HTTPException(status_code=400, detail="draft.rule_id is required")
        existing = db.query(WorkspaceCustomRule).filter(
            WorkspaceCustomRule.workspace_id == ws_uuid,
            WorkspaceCustomRule.rule_id == rule_id,
        ).first()
        if existing:
            raise HTTPException(status_code=409, detail=f"Rule '{rule_id}' already exists")
        if pattern := req.draft.get("match_pattern"):
            import re
            try:
                re.compile(pattern)
            except re.error as e:
                raise HTTPException(status_code=400, detail=f"Invalid match_pattern regex: {e}")
        body = {k: v for k, v in req.draft.items() if k not in ("rule_id", "persona")}
        body["id"] = rule_id
        rule = WorkspaceCustomRule(
            workspace_id=ws_uuid,
            rule_id=rule_id,
            persona=req.draft.get("persona", "agent"),
            body=body,
            enabled=True,
        )
        db.add(rule)
        db.commit()
        return {"ok": True, "rule_id": rule_id, "action": "created"}

    elif req.action == "patch":
        from app.modules.guard.routers.policies import _upsert_override
        rule_id = req.target_rule_id
        if not rule_id:
            raise HTTPException(status_code=400, detail="target_rule_id is required for patch")
        if pattern := req.draft.get("match_pattern"):
            import re
            try:
                re.compile(pattern)
            except re.error as e:
                raise HTTPException(status_code=400, detail=f"Invalid match_pattern regex: {e}")
        custom = db.query(WorkspaceCustomRule).filter(
            WorkspaceCustomRule.workspace_id == ws_uuid,
            WorkspaceCustomRule.rule_id == rule_id,
        ).first()
        if custom:
            if "enabled" in req.draft:
                custom.enabled = req.draft["enabled"]
            body_patch = {k: v for k, v in req.draft.items() if k != "enabled"}
            if body_patch:
                custom.body = {**custom.body, **body_patch}
            custom.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {"ok": True, "rule_id": rule_id, "action": "patched"}
        touched = False
        if "enabled" in req.draft:
            _upsert_override(db, ws_uuid, rule_id, disabled=not req.draft["enabled"])
            touched = True
        action_val = req.draft.get("action")
        msg_val = req.draft.get("message")
        pat_val = req.draft.get("match_pattern")
        if action_val or msg_val or pat_val:
            _upsert_override(db, ws_uuid, rule_id, action=action_val, message=msg_val, match_pattern=pat_val)
            touched = True
        if not touched:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
        db.commit()
        return {"ok": True, "rule_id": rule_id, "action": "patched"}

    elif req.action == "delete":
        rule_id = req.target_rule_id or req.draft.get("rule_id")
        if not rule_id:
            raise HTTPException(status_code=400, detail="target_rule_id is required for delete")
        rule = db.query(WorkspaceCustomRule).filter(
            WorkspaceCustomRule.workspace_id == ws_uuid,
            WorkspaceCustomRule.rule_id == rule_id,
        ).first()
        if not rule:
            raise HTTPException(status_code=404, detail=f"Rule '{rule_id}' not found")
        db.delete(rule)
        db.commit()
        return {"ok": True, "rule_id": rule_id, "action": "deleted"}

    raise HTTPException(status_code=400, detail=f"Unknown action '{req.action}'")
