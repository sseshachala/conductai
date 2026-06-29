"""ConductGuard — policy endpoints.

GET    /guard/policies                — list custom + active pack rules
POST   /guard/policies                — create a custom rule
PATCH  /guard/policies/{rule_id}      — edit a rule (custom row OR pack override)
DELETE /guard/policies/{rule_id}      — delete a custom rule (pack rules can't be deleted)
POST   /guard/policies/generate       — LLM-generate a rule from a description
GET    /guard/policies/sync           — daemon sync, returns the active ruleset
POST   /guard/policies/reinstall-base — re-install the conduct-base pack
"""
from __future__ import annotations

import hashlib
import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, get_guard_hook_auth
from app.core.database import get_db
from app.modules.guard.models import (
    GuardAuditEvent,
    GuardConfig,
    GuardRuleOverride,
    SkillPack,
    WorkspaceCustomRule,
    WorkspaceSkillPack,
)
from app.modules.guard.policy_engine import compute_policy, invalidate_policy_cache

router = APIRouter(prefix="/guard/policies", tags=["guard-policies"])

_VALID_ACTIONS = {"block", "warn", "audit", "approval", "inject"}
_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_GENERATE_SYSTEM_FILE = _PROMPTS_DIR / "policy_generate_system.txt"
_GENERATE_SYSTEM = _GENERATE_SYSTEM_FILE.read_text() if _GENERATE_SYSTEM_FILE.exists() else ""


# ── Schemas ───────────────────────────────────────────────────────────────────

class PolicyOut(BaseModel):
    """Workspace policy as surfaced to the UI. Same shape for custom rules and
    pack rules; the `pack_id` field distinguishes them (None for custom)."""
    id: str
    workspace_id: str
    rule_id: str
    description: Optional[str] = None
    match_tool: Optional[str] = None
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: str
    message: Optional[str] = None
    enabled: bool
    builtin: bool
    pack_id: Optional[str] = None
    persona: str = "agent"
    non_overridable: bool = False
    persona_affinity: list[str] = []
    recommendation: Optional[str] = None
    frameworks: list[str] = []
    severity: str = "medium"
    iso_control: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class PolicyCreate(BaseModel):
    rule_id: str
    description: Optional[str] = None
    match_tool: Optional[str] = None
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: str
    message: Optional[str] = None
    persona: str = "agent"
    persona_affinity: Optional[list[str]] = None
    recommendation: Optional[str] = None
    frameworks: Optional[list[str]] = None
    severity: Optional[str] = None
    iso_control: Optional[str] = None
    workspace_id: Optional[str] = None


class PolicyPatch(BaseModel):
    enabled: Optional[bool] = None
    description: Optional[str] = None
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: Optional[str] = None
    message: Optional[str] = None


class PolicySyncRule(BaseModel):
    rule_id: str
    match_tool: Optional[str] = None
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: str
    message: Optional[str] = None


class PolicySyncOut(BaseModel):
    workspace_id: str
    version: str
    persona: str
    fail_mode: str = "fail_open"   # CLI hook reads this to decide outage behavior
    rules: list[PolicySyncRule]
    signature: Optional[str] = None    # HMAC-SHA256 hex; present when workspace has a signing key
    signed_at: Optional[str] = None    # ISO-8601 timestamp of when the signature was computed


class PolicyGenerateRequest(BaseModel):
    prompt: str
    workspace_id: Optional[str] = None
    environment_id: Optional[str] = None


class PolicyGenerateOut(BaseModel):
    rule_id: str
    description: str
    match_tool: str
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: str
    message: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ws_uuid(workspace_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")


def _custom_to_out(row: WorkspaceCustomRule) -> PolicyOut:
    body = row.body or {}
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
    return PolicyOut(
        id=rule["id"],
        workspace_id=str(workspace_id),
        rule_id=rule["id"],
        description=rule.get("description"),
        match_tool=rule.get("match_tool"),
        match_pattern=(override.match_pattern if override and override.match_pattern else rule.get("match_pattern")),
        match_path_pattern=rule.get("match_path_pattern"),
        action=(override.action if override and override.action else rule.get("action", "block")),
        message=(override.custom_message if override and override.custom_message else rule.get("message")),
        enabled=not (override and override.disabled),
        builtin=True,
        pack_id=pack_slug,
        persona=rule.get("persona") or "agent",
        non_overridable=bool(rule.get("non_overridable", False)),
        persona_affinity=rule.get("persona_affinity") or [],
        recommendation=rule.get("recommendation"),
        frameworks=rule.get("frameworks") or [],
        severity=rule.get("severity") or "medium",
        iso_control=rule.get("iso_control"),
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
) -> None:
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
        existing.overridden_at = now
    else:
        db.add(GuardRuleOverride(
            workspace_id=workspace_id,
            rule_id=rule_id,
            disabled=bool(disabled) if disabled is not None else False,
            action=action,
            custom_message=message,
            match_pattern=match_pattern,
            overridden_at=now,
        ))


def _write_audit(db: Session, workspace_id: uuid.UUID, tool_call: str, rule_id: str, action: str) -> None:
    """Non-fatal audit row for policy mutations."""
    try:
        db.add(GuardAuditEvent(
            workspace_id=workspace_id,
            clerk_user_id=None,
            ai_tool="platform",
            tool_call=tool_call,
            decision="allowed",
            rule_id=rule_id,
            input_summary=f"rule_id={rule_id} action={action}"[:500],
            ts=datetime.now(timezone.utc),
        ))
        db.commit()
    except Exception:
        db.rollback()


def _get_anthropic_key(db: Session, workspace_id: Optional[str]) -> str:
    """Resolve the workspace's Anthropic API key from the credential vault."""
    if not workspace_id:
        return ""
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return ""
    from app.core.crypto import decrypt
    from app.models.integration import Integration
    row = (
        db.query(Integration)
        .filter(Integration.workspace_id == ws_uuid, Integration.handle == "anthropic")
        .first()
    )
    if not row or not row.encrypted_credentials:
        return ""
    try:
        creds = decrypt(row.encrypted_credentials)
        return creds.get("api_key") or ""
    except Exception:
        return ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=PolicyGenerateOut)
def generate_policy(
    body: PolicyGenerateRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """LLM-generate a rule from a plain-English description."""
    import anthropic
    from app.routers.generate import _resolve_anthropic_key

    resolved_ws = body.workspace_id or workspace_id
    api_key = _resolve_anthropic_key(resolved_ws, body.environment_id, db) or os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        env_hint = "selected environment" if body.environment_id else "Default environment"
        raise HTTPException(
            status_code=503,
            detail=f"Anthropic API key not configured for the {env_hint} — add it in Settings -> Environments",
        )

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_GENERATE_SYSTEM,
            messages=[{"role": "user", "content": body.prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=422,
            detail="Could not generate a rule from that description — try being more specific.",
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Rule generation failed — check that your Anthropic API key is valid in Settings -> Environments.",
        )

    action = data.get("action", "block")
    if action not in _VALID_ACTIONS:
        action = "block"

    return PolicyGenerateOut(
        rule_id=data.get("rule_id", "custom-rule"),
        description=data.get("description", ""),
        match_tool=data.get("match_tool", "*"),
        match_pattern=data.get("match_pattern") or None,
        match_path_pattern=data.get("match_path_pattern") or None,
        action=action,
        message=data.get("message", ""),
    )


@router.get("/sync", response_model=PolicySyncOut)
def sync_policies(
    workspace_id: str = Query(...),
    db: Session = Depends(get_db),
    _auth: str = Depends(get_guard_hook_auth),
):
    """Return the current active ruleset for the hook binary or MCP server.

    When the workspace has a signing key configured, the response includes a
    HMAC-SHA256 signature field. The canonical body used for signing is the
    JSON-serialised dict of all fields except signature and signed_at,
    with keys sorted and no extra whitespace.
    """
    import hmac as _hmac
    from app.modules.guard.models import WorkspaceSigningKey

    ws_uuid = _ws_uuid(workspace_id)

    gc = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    persona = (gc.persona if gc and gc.persona else "standard")

    active_rules = compute_policy(db, ws_uuid, persona)
    version_hash = hashlib.sha256(json.dumps(active_rules, sort_keys=True).encode()).hexdigest()[:16]
    version = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}-{version_hash}"

    out = PolicySyncOut(
        workspace_id=workspace_id,
        version=version,
        persona=persona,
        fail_mode=getattr(gc, "fail_mode", "fail_open") if gc else "fail_open",
        rules=[
            PolicySyncRule(
                rule_id=r["id"],
                match_tool=r.get("match_tool"),
                match_pattern=r.get("match_pattern"),
                match_path_pattern=r.get("match_path_pattern"),
                action=r["action"],
                message=r.get("message"),
            )
            for r in active_rules
        ],
    )

    # Sign the response if the workspace has a signing key.
    signing_key_row = db.get(WorkspaceSigningKey, ws_uuid)
    if signing_key_row and signing_key_row.key_bytes:
        signed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        body_dict = out.model_dump(exclude={"signature", "signed_at"})
        body_dict["rules"] = [r.model_dump() for r in out.rules]
        canonical = json.dumps(body_dict, sort_keys=True, separators=(",", ":"))
        sig = _hmac.new(signing_key_row.key_bytes, canonical.encode(), hashlib.sha256).hexdigest()
        out.signature = sig
        out.signed_at = signed_at

    return out


@router.get("", response_model=list[PolicyOut])
def list_policies(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """List all policies for a workspace — custom rules + active pack rules."""
    ws_uuid = _ws_uuid(workspace_id)

    out: list[PolicyOut] = []

    # 1. Custom rules
    customs = (
        db.query(WorkspaceCustomRule)
        .filter(WorkspaceCustomRule.workspace_id == ws_uuid)
        .order_by(WorkspaceCustomRule.created_at.asc())
        .all()
    )
    out.extend(_custom_to_out(c) for c in customs)

    # 2. Pack rules (with overrides applied)
    installed = (
        db.query(WorkspaceSkillPack)
        .filter(WorkspaceSkillPack.workspace_id == ws_uuid)
        .order_by(WorkspaceSkillPack.installed_at)
        .all()
    )
    overrides = {
        o.rule_id: o
        for o in db.query(GuardRuleOverride)
        .filter(GuardRuleOverride.workspace_id == ws_uuid)
        .all()
    }
    seen: set[str] = set()
    for wp in installed:
        pack = (
            db.query(SkillPack)
            .filter(SkillPack.slug == wp.pack_slug)
            .order_by(SkillPack.version.desc())
            .first()
        )
        if not pack:
            continue
        for rule in pack.rules or []:
            if rule["id"] in seen:
                continue
            seen.add(rule["id"])
            out.append(_pack_rule_to_out(rule, wp.pack_slug, wp.installed_at, ws_uuid, overrides.get(rule["id"])))

    return out


@router.post("", response_model=PolicyOut, status_code=201)
def create_policy(
    body: PolicyCreate,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Create a custom (non-pack) policy rule."""
    if body.action not in _VALID_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action '{body.action}'. Must be one of: {sorted(_VALID_ACTIONS)}",
        )

    resolved_ws = body.workspace_id or workspace_id
    ws_uuid = _ws_uuid(resolved_ws)

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
        "persona_affinity": body.persona_affinity or ["conservative", "standard", "developer"],
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

    _write_audit(db, ws_uuid, "policy_created", body.rule_id, body.action)
    return _custom_to_out(row)


@router.patch("/{rule_id}", response_model=PolicyOut)
def patch_policy(
    rule_id: str,
    body: PolicyPatch,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
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
        _write_audit(db, ws_uuid, "policy_updated", rule_id, b.get("action", "block"))
        return _custom_to_out(custom)

    # Pack rule -> write override
    touched_override = False
    if body.enabled is not None:
        _upsert_override(db, ws_uuid, rule_id, disabled=not body.enabled)
        touched_override = True
    if body.action is not None or body.message is not None or body.match_pattern is not None:
        _upsert_override(db, ws_uuid, rule_id, action=body.action, message=body.message, match_pattern=body.match_pattern)
        touched_override = True
    if touched_override:
        db.commit()
        invalidate_policy_cache(db, ws_uuid)
        _write_audit(db, ws_uuid, "policy_override_set", rule_id, body.action or "")

    # Re-synthesize PolicyOut from the pack rule + the (possibly new) override
    override = db.get(GuardRuleOverride, (ws_uuid, rule_id))
    installed = (
        db.query(WorkspaceSkillPack)
        .filter(WorkspaceSkillPack.workspace_id == ws_uuid)
        .order_by(WorkspaceSkillPack.installed_at)
        .all()
    )
    for wp in installed:
        pack = (
            db.query(SkillPack).filter(SkillPack.slug == wp.pack_slug)
            .order_by(SkillPack.version.desc()).first()
        )
        if not pack:
            continue
        for rule in pack.rules or []:
            if rule["id"] == rule_id:
                return _pack_rule_to_out(rule, wp.pack_slug, wp.installed_at, ws_uuid, override)

    raise HTTPException(status_code=404, detail="Policy not found")


@router.delete("/{rule_id}", status_code=204)
def delete_policy(
    rule_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
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
    _write_audit(db, ws_uuid, "policy_deleted", rule_id, "")


@router.post("/reinstall-base")
def reinstall_base(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
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
