"""ConductGuard policies — shared helpers (scoping, row projection, overrides, audit, exceptions)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import HTTPException
from sqlalchemy.orm import Session
from app.models.workspace import Workspace
from app.modules.guard.models import (
    GuardAuditEvent,
    GuardRuleOverride,
    SkillPack,
    WorkspaceCustomRule,
    WorkspaceSkillPack,
)
from app.modules.guard.policy_engine import (
    VALID_ACTIONS,
    _get_pack,
    is_action_relaxing,
    is_exception_active,
)
from app.modules.guard.enforcement import (
    derive_gates,
    derive_surface_status,
)
from app.modules.guard.routers.policies_schemas import (
    PolicyOut,
)


_VALID_ACTIONS = set(VALID_ACTIONS)


def _bg_project_rule(workspace_id: str, rule_id: str) -> None:
    """Background task: project a WorkspaceCustomRule into the knowledge index."""
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        from app.modules.guard.knowledge import project_rule
        from app.modules.guard.models import WorkspaceCustomRule as _WCR
        import uuid as _uuid
        ws_uuid = _uuid.UUID(workspace_id)
        rule = db.get(_WCR, (ws_uuid, rule_id))
        if rule:
            project_rule(rule, db)
    except Exception as exc:
        import structlog
        structlog.get_logger().warning(
            "guard.knowledge.bg_project_rule_failed",
            rule_id=rule_id,
            error=str(exc),
        )
    finally:
        db.close()


_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


_GENERATE_SYSTEM_FILE = _PROMPTS_DIR / "policy_generate_system.txt"


_GENERATE_SYSTEM = _GENERATE_SYSTEM_FILE.read_text() if _GENERATE_SYSTEM_FILE.exists() else ""


def _ws_uuid(workspace_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")


def _org_ws_subquery(db: Session, workspace_id: str):
    """Strict single-workspace scoping. See issue #1564.

    Previously this broadened queries to every workspace in the same org or
    (fallback) every workspace the current user owned — silently leaking data
    across tenants on every list endpoint. Legit org-wide rollups must ship as
    explicit /org/* endpoints gated on `guard.*.view_all` permissions.
    """
    ws_uuid = _ws_uuid(workspace_id)
    return db.query(Workspace.id).filter(Workspace.id == ws_uuid)


def _custom_to_out(row: WorkspaceCustomRule) -> PolicyOut:
    body = row.body or {}
    # #1733: derive_gates needs a persona hint. Custom rules store persona
    # on the ORM row, not the body dict — inject a shallow copy so the
    # helper sees it without mutating the underlying JSONB.
    body_for_gates = {**body, "persona": body.get("persona") or row.persona or "agent"}
    return PolicyOut(
        id=row.rule_id,
        workspace_id=str(row.workspace_id),
        rule_id=row.rule_id,
        description=body.get("description"),
        match_tool=body.get("match_tool"),
        match_pattern=body.get("match_pattern"),
        match_path_pattern=body.get("match_path_pattern"),
        action=body.get("action", "block"),
        message=body.get("message"),
        enabled=bool(row.enabled),
        builtin=False,
        pack_id=None,
        persona=row.persona or "agent",
        non_overridable=False,
        persona_affinity=body.get("persona_affinity") or [],
        recommendation=body.get("recommendation"),
        frameworks=body.get("frameworks") or [],
        severity=body.get("severity") or "medium",
        iso_control=body.get("iso_control"),
        gates=derive_gates(body_for_gates),
        derived_mcp=derive_surface_status(body_for_gates, "mcp"),
        derived_proxy=derive_surface_status(body_for_gates, "proxy"),
        derived_runtime=derive_surface_status(body_for_gates, "runtime"),
        derived_hook=derive_surface_status(body_for_gates, "hook"),
        guarantee=(body.get("enforcement") or {}).get("guarantee"),
        known_limitations=(body.get("enforcement") or {}).get("known_limitations") or [],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _pack_rule_to_out(
    rule: dict,
    pack_slug: str,
    installed_at: datetime,
    workspace_id: uuid.UUID,
    override: Optional[GuardRuleOverride],
) -> PolicyOut:
    base_action = rule.get("action", "block")
    relaxing = bool(
        override
        and (override.disabled or is_action_relaxing(base_action, override.action))
    )
    active = bool(override and is_exception_active(override, base_action))
    expired = bool(
        relaxing
        and override
        and override.expires_at is not None
        and override.expires_at <= datetime.now(timezone.utc)
    )
    effective_action = base_action
    effective_enabled = True
    if override:
        if override.action in VALID_ACTIONS and (not relaxing or active):
            effective_action = override.action
        if override.disabled and active:
            effective_enabled = False

    return PolicyOut(
        id=rule["id"],
        workspace_id=str(workspace_id),
        rule_id=rule["id"],
        description=rule.get("description"),
        match_tool=rule.get("match_tool"),
        match_pattern=(override.match_pattern if override and override.match_pattern else rule.get("match_pattern")),
        match_path_pattern=rule.get("match_path_pattern"),
        action=effective_action,
        message=(override.custom_message if override and override.custom_message else rule.get("message")),
        enabled=effective_enabled,
        builtin=True,
        pack_id=pack_slug,
        persona=rule.get("persona") or "agent",
        non_overridable=bool(rule.get("non_overridable", False)),
        persona_affinity=rule.get("persona_affinity") or [],
        recommendation=rule.get("recommendation"),
        frameworks=rule.get("frameworks") or [],
        severity=rule.get("severity") or "medium",
        iso_control=rule.get("iso_control"),
        tag=rule.get("tag"),
        gates=derive_gates(rule),
        derived_mcp=derive_surface_status(rule, "mcp"),
        derived_proxy=derive_surface_status(rule, "proxy"),
        derived_runtime=derive_surface_status(rule, "runtime"),
        derived_hook=derive_surface_status(rule, "hook"),
        guarantee=(rule.get("enforcement") or {}).get("guarantee"),
        known_limitations=(rule.get("enforcement") or {}).get("known_limitations") or [],
        exception_reason=override.reason if override and relaxing else None,
        exception_expires_at=override.expires_at if override and relaxing else None,
        exception_active=active,
        exception_expired=expired,
        created_at=installed_at,
        updated_at=installed_at,
    )


def _upsert_override(
    db: Session,
    workspace_id: uuid.UUID,
    rule_id: str,
    *,
    disabled: Optional[bool] = None,
    action: Optional[str] = None,
    message: Optional[str] = None,
    match_pattern: Optional[str] = None,
    reason: Optional[str] = None,
    expires_at: Optional[datetime] = None,
    overridden_by: Optional[str] = None,
    clear_exception: bool = False,
    reset_use_audit: bool = False,
) -> GuardRuleOverride:
    """Create or update a GuardRuleOverride. Fields with `None` are not touched."""
    existing = db.get(GuardRuleOverride, (workspace_id, rule_id))
    now = datetime.now(timezone.utc)
    if existing:
        if disabled is not None:
            existing.disabled = disabled
        if action is not None:
            existing.action = action
        if message is not None:
            existing.custom_message = message
        if match_pattern is not None:
            existing.match_pattern = match_pattern
        if clear_exception:
            existing.reason = None
            existing.expires_at = None
            existing.use_audited_at = None
            existing.expiry_audited_at = None
        else:
            if reason is not None:
                existing.reason = reason
            if expires_at is not None:
                existing.expires_at = expires_at
        if reset_use_audit:
            existing.use_audited_at = None
            existing.expiry_audited_at = None
        existing.overridden_by = overridden_by
        existing.overridden_at = now
        return existing
    else:
        row = GuardRuleOverride(
            workspace_id=workspace_id,
            rule_id=rule_id,
            disabled=bool(disabled) if disabled is not None else False,
            action=action,
            custom_message=message,
            match_pattern=match_pattern,
            reason=None if clear_exception else reason,
            expires_at=None if clear_exception else expires_at,
            overridden_by=overridden_by,
            overridden_at=now,
        )
        db.add(row)
        return row


def _write_audit(
    db: Session,
    workspace_id: uuid.UUID,
    tool_call: str,
    rule_id: str,
    action: str,
    *,
    actor_id: Optional[str] = None,
    details: Optional[str] = None,
) -> None:
    """Non-fatal audit row for policy mutations."""
    try:
        from app.modules.guard.models import chain_hash_for_insert
        ts = datetime.now(timezone.utc)
        prev_h, entry_h = chain_hash_for_insert(db, workspace_id, ts, tool_call, "allowed")
        db.add(GuardAuditEvent(
            workspace_id=workspace_id,
            clerk_user_id=actor_id,
            ai_tool="platform",
            tool_call=tool_call,
            decision="allowed",
            rule_id=rule_id,
            input_summary=(details or f"rule_id={rule_id} action={action}")[:500],
            ts=ts,
            previous_hash=prev_h,
            entry_hash=entry_h,
        ))
        db.commit()
    except Exception:
        db.rollback()


def _find_pack_rule(
    db: Session,
    workspace_id: uuid.UUID,
    rule_id: str,
) -> tuple[dict, WorkspaceSkillPack] | None:
    installed = (
        db.query(WorkspaceSkillPack)
        .filter(WorkspaceSkillPack.workspace_id == workspace_id)
        .order_by(WorkspaceSkillPack.installed_at)
        .all()
    )
    for wp in installed:
        pack = _resolve_workspace_pack(db, wp)
        if not pack:
            continue
        for rule in pack.rules or []:
            if rule["id"] == rule_id:
                return rule, wp
    return None


def _resolve_workspace_pack(
    db: Session,
    workspace_pack: WorkspaceSkillPack,
) -> Optional[SkillPack]:
    """Resolve the exact pack version enforced for a workspace installation."""
    return _get_pack(
        db,
        workspace_pack.pack_slug,
        workspace_pack.pinned_version,
    )


def _validate_exception_metadata(
    *,
    relaxing: bool,
    fields_touched: bool,
    reason: Optional[str],
    expires_at: Optional[datetime],
) -> tuple[Optional[str], Optional[datetime]]:
    if relaxing and fields_touched:
        if not reason or not reason.strip():
            raise HTTPException(
                status_code=422,
                detail="A non-empty reason is required for a relaxing policy exception",
            )
        if expires_at is None or expires_at.tzinfo is None:
            raise HTTPException(
                status_code=422,
                detail="expires_at must include a timezone and be in the future",
            )
        if expires_at <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=422,
                detail="expires_at must be a future timestamp for a relaxing policy exception",
            )
        return reason.strip(), expires_at
    if not relaxing and (reason is not None or expires_at is not None):
        raise HTTPException(
            status_code=422,
            detail="reason and expires_at are only valid for relaxing policy exceptions",
        )
    return reason, expires_at


def _audit_exception_transitions(
    db: Session,
    workspace_id: uuid.UUID,
    *,
    audit_use: bool,
) -> None:
    """Write at-most-once use/expiry events for the current exception version."""
    now = datetime.now(timezone.utc)
    overrides = (
        db.query(GuardRuleOverride)
        .filter(GuardRuleOverride.workspace_id == workspace_id)
        .all()
    )
    for override in overrides:
        found = _find_pack_rule(db, workspace_id, override.rule_id)
        if not found:
            continue
        rule, _ = found
        base_action = rule.get("action", "block")
        relaxing = bool(
            override.disabled or is_action_relaxing(base_action, override.action)
        )
        if not relaxing:
            continue
        active = is_exception_active(override, base_action, now=now)
        if active and audit_use and override.use_audited_at is None:
            override.use_audited_at = now
            _write_audit(
                db,
                workspace_id,
                "policy_exception_used",
                override.rule_id,
                override.action or "disabled",
                details=(
                    f"rule_id={override.rule_id} reason={override.reason} "
                    f"expires_at={override.expires_at.isoformat()}"
                ),
            )
        elif (
            not active
            and override.expires_at is not None
            and override.expires_at <= now
            and override.expiry_audited_at is None
        ):
            override.expiry_audited_at = now
            _write_audit(
                db,
                workspace_id,
                "policy_exception_expired",
                override.rule_id,
                override.action or "disabled",
                details=(
                    f"rule_id={override.rule_id} reason={override.reason} "
                    f"expired_at={override.expires_at.isoformat()}"
                ),
            )


def _get_anthropic_key(db: Session, workspace_id: Optional[str]) -> str:
    """Resolve the workspace's Anthropic API key from the credential vault."""
    if not workspace_id:
        return ""
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return ""
    from app.core.credentials import get_credential
    try:
        creds = get_credential(db, str(ws_uuid), "anthropic")
        return creds.get("api_key") or ""
    except Exception:
        return ""
