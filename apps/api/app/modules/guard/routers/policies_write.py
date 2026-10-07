"""ConductGuard policies — create, patch, delete and reinstall endpoints."""

from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.auth import (
    get_user_id,
    get_workspace_id,
    require_permission,
)
from app.core.database import get_db
from app.modules.guard.models import (
    GuardRuleOverride,
    WorkspaceCustomRule,
    WorkspaceSkillPack,
)
from app.modules.guard.policy_engine import (
    VALID_ACTIONS,
    invalidate_policy_cache,
    is_action_relaxing,
)
from app.modules.guard.routers.policies_schemas import (
    PolicyCreate,
    PolicyOut,
    PolicyPatch,
)
from app.modules.guard.routers.policies_helpers import (
    _VALID_ACTIONS,
    _bg_project_rule,
    _custom_to_out,
    _find_pack_rule,
    _pack_rule_to_out,
    _upsert_override,
    _validate_exception_metadata,
    _write_audit,
    _ws_uuid,
)

router = APIRouter(prefix="/guard/policies", tags=["guard-policies"])


@router.post("", response_model=PolicyOut, status_code=201)
def create_policy(
    body: PolicyCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _: str = Depends(require_permission("guard.policies.edit")),
):
    """Create a custom (non-pack) policy rule."""
    if body.action not in _VALID_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action '{body.action}'. Must be one of: {sorted(_VALID_ACTIONS)}",
        )

    if body.workspace_id is not None and body.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Policy workspace does not match authorized workspace")
    resolved_ws = workspace_id
    ws_uuid = _ws_uuid(workspace_id)

    existing = db.get(WorkspaceCustomRule, (ws_uuid, body.rule_id))
    if existing:
        raise HTTPException(status_code=409, detail=f"Rule '{body.rule_id}' already exists in this workspace")

    rule_body = {
        "id": body.rule_id,
        "description": body.description,
        "match_tool": body.match_tool,
        "match_pattern": body.match_pattern,
        "match_path_pattern": body.match_path_pattern,
        "action": body.action,
        "message": body.message,
        # ``proxy`` renamed to ``gateway`` (2026-09-22) — both names still
        # accepted on read, but new writes default to the current name.
        "persona_affinity": body.persona_affinity or ["agent", "gateway"],
        "recommendation": body.recommendation,
        "frameworks": body.frameworks or [],
        "severity": body.severity or "medium",
        "iso_control": body.iso_control,
    }
    rule_body = {k: v for k, v in rule_body.items() if v is not None}

    row = WorkspaceCustomRule(
        workspace_id=ws_uuid,
        rule_id=body.rule_id,
        persona=body.persona,
        body=rule_body,
        enabled=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    invalidate_policy_cache(db, ws_uuid)

    _write_audit(
        db, ws_uuid, "policy_created", body.rule_id, body.action, actor_id=user_id
    )
    background_tasks.add_task(_bg_project_rule, resolved_ws, body.rule_id)
    return _custom_to_out(row)


@router.patch("/{rule_id}", response_model=PolicyOut)
def patch_policy(
    rule_id: str,
    body: PolicyPatch,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _: str = Depends(require_permission("guard.policies.edit")),
):
    """Edit a rule. Custom rules update workspace_custom_rules; pack rules write
    an entry in guard_rule_overrides."""
    if body.action is not None and body.action not in _VALID_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action '{body.action}'. Must be one of: {sorted(_VALID_ACTIONS)}",
        )

    ws_uuid = _ws_uuid(workspace_id)

    # Custom rule?
    custom = db.get(WorkspaceCustomRule, (ws_uuid, rule_id))
    if custom is not None:
        b = dict(custom.body or {})
        if body.description is not None: b["description"] = body.description
        if body.match_pattern is not None: b["match_pattern"] = body.match_pattern
        if body.match_path_pattern is not None: b["match_path_pattern"] = body.match_path_pattern
        if body.action is not None: b["action"] = body.action
        if body.message is not None: b["message"] = body.message
        custom.body = b
        if body.enabled is not None:
            custom.enabled = body.enabled
        custom.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(custom)
        invalidate_policy_cache(db, ws_uuid)
        _write_audit(
            db,
            ws_uuid,
            "policy_updated",
            rule_id,
            b.get("action", "block"),
            actor_id=user_id,
        )
        background_tasks.add_task(_bg_project_rule, workspace_id, rule_id)
        return _custom_to_out(custom)

    found = _find_pack_rule(db, ws_uuid, rule_id)
    if not found:
        raise HTTPException(status_code=404, detail="Policy not found")
    rule, wp = found
    base_action = rule.get("action", "block")
    if base_action not in VALID_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Pack rule has unsupported action '{base_action}'",
        )

    existing = db.get(GuardRuleOverride, (ws_uuid, rule_id))
    target_disabled = (
        not body.enabled
        if body.enabled is not None
        else bool(existing.disabled) if existing else False
    )
    target_action = (
        body.action
        if body.action is not None
        else existing.action if existing else None
    )
    relaxing = bool(
        target_disabled or is_action_relaxing(base_action, target_action)
    )
    exception_fields_touched = (
        body.enabled is not None
        or body.action is not None
        or body.reason is not None
        or body.expires_at is not None
    )

    reason = body.reason if body.reason is not None else existing.reason if existing else None
    expires_at = (
        body.expires_at
        if body.expires_at is not None
        else existing.expires_at if existing else None
    )
    validation_reason = reason if relaxing else body.reason
    validation_expiry = expires_at if relaxing else body.expires_at
    reason, expires_at = _validate_exception_metadata(
        relaxing=relaxing,
        fields_touched=exception_fields_touched,
        reason=validation_reason,
        expires_at=validation_expiry,
    )

    touched_override = any(
        value is not None
        for value in (
            body.enabled,
            body.action,
            body.message,
            body.match_pattern,
            body.reason,
            body.expires_at,
        )
    )
    if touched_override:
        created = existing is None
        override = _upsert_override(
            db,
            ws_uuid,
            rule_id,
            disabled=not body.enabled if body.enabled is not None else None,
            action=body.action,
            message=body.message,
            match_pattern=body.match_pattern,
            reason=reason if relaxing else None,
            expires_at=expires_at if relaxing else None,
            overridden_by=user_id,
            clear_exception=not relaxing,
            reset_use_audit=relaxing and exception_fields_touched,
        )
        db.commit()
        invalidate_policy_cache(db, ws_uuid)
        event_name = (
            "policy_exception_created"
            if relaxing and created
            else "policy_exception_updated"
            if relaxing
            else "policy_override_set"
        )
        details = (
            f"rule_id={rule_id} action={target_action or base_action} "
            f"disabled={target_disabled}"
        )
        if relaxing:
            details += f" reason={reason} expires_at={expires_at.isoformat()}"
        _write_audit(
            db,
            ws_uuid,
            event_name,
            rule_id,
            target_action or ("disabled" if target_disabled else base_action),
            actor_id=user_id,
            details=details,
        )
    else:
        override = existing

    return _pack_rule_to_out(
        rule, wp.pack_slug, wp.installed_at, ws_uuid, override
    )


@router.delete("/{rule_id}", status_code=204)
def delete_policy(
    rule_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    _: str = Depends(require_permission("guard.policies.edit")),
):
    """Delete a custom rule. Pack rules cannot be deleted — uninstall the pack
    or disable the rule via PATCH /guard/policies/{rule_id} (enabled=False)."""
    ws_uuid = _ws_uuid(workspace_id)

    custom = db.get(WorkspaceCustomRule, (ws_uuid, rule_id))
    if custom is None:
        raise HTTPException(
            status_code=403,
            detail="Pack rules cannot be deleted. Uninstall the pack or disable the rule.",
        )
    db.delete(custom)
    db.commit()
    invalidate_policy_cache(db, ws_uuid)
    _write_audit(db, ws_uuid, "policy_deleted", rule_id, "", actor_id=user_id)


@router.post("/reinstall-base")
def reinstall_base(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.edit")),
):
    """Re-install the conduct-base skill pack if missing, then invalidate cache."""
    ws_uuid = _ws_uuid(workspace_id)
    existing = db.get(WorkspaceSkillPack, (ws_uuid, "conduct-base"))
    if not existing:
        db.add(WorkspaceSkillPack(
            workspace_id=ws_uuid,
            pack_slug="conduct-base",
            installed_by="system:reinstall",
            installed_at=datetime.now(timezone.utc),
        ))
        db.commit()
    invalidate_policy_cache(db, ws_uuid)
    return {"status": "ok", "pack": "conduct-base"}
