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
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import (
    get_guard_hook_auth,
    get_user_id,
    get_workspace_id,
    require_permission,
)
from app.core.database import get_db
from app.models.workspace import Workspace
from app.modules.guard.models import (
    GuardAuditEvent,
    GuardConfig,
    GuardRuleOverride,
    SkillPack,
    WorkspaceCustomRule,
    WorkspaceSkillPack,
)
from app.modules.guard.policy_engine import (
    VALID_ACTIONS,
    _get_pack,
    compute_policy,
    invalidate_policy_cache,
    is_action_relaxing,
    is_exception_active,
)
from app.modules.guard.coverage import workspace_coverage_matrix
from app.modules.guard.enforcement import is_hook_applicable_rule

router = APIRouter(prefix="/guard/policies", tags=["guard-policies"])

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
    tag: Optional[str] = None
    exception_reason: Optional[str] = None
    exception_expires_at: Optional[datetime] = None
    exception_active: bool = False
    exception_expired: bool = False
    last_triggered: Optional[datetime] = None
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
    reason: Optional[str] = None
    expires_at: Optional[datetime] = None


class PolicySyncRule(BaseModel):
    rule_id: str
    match_tool: Optional[str] = None
    match_ai_tool: Optional[str] = None
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: str
    message: Optional[str] = None


class PolicySyncOut(BaseModel):
    workspace_id: str
    version: str
    persona: str
    fail_mode: str = "fail_open"   # CLI hook reads this to decide outage behavior
    advisory_mode: bool = False     # CLI hook reads this to skip blocking
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


class EnforcementCoverageOut(BaseModel):
    rule_id: str
    name: str
    pack: Optional[str] = None
    pack_version: Optional[str] = None
    builtin: bool
    personas: list[str]
    action: str
    base_action: str
    enabled: bool
    proxy: Literal["hard", "conditional", "advisory", "not_supported"]
    hook: Literal["hard", "conditional", "advisory", "not_supported"]
    mcp: Literal["hard", "conditional", "advisory", "not_supported"]
    runtime: Literal["hard", "conditional", "advisory", "not_supported"]
    guarantee: str
    requires: list[str]
    known_limitations: list[str]
    enforcement_version: Literal[1]
    exception_reason: Optional[str] = None
    exception_expires_at: Optional[datetime] = None
    exception_active: bool = False
    exception_expired: bool = False


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=PolicyGenerateOut)
def generate_policy(
    body: PolicyGenerateRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.edit")),
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

    try:
        from app.runtime.llm_client import client_for, LLMTextBlock
        client = client_for("anthropic", api_key)
        response = client.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            system=_GENERATE_SYSTEM,
            messages=[{"role": "user", "content": body.prompt}],
        )
        first = response.content[0] if response.content else None
        raw = first.text.strip() if isinstance(first, LLMTextBlock) else ""
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
    # ponytail: sync always uses surface="agent" — GuardConfig.persona is developer type, not surface
    active_rules = compute_policy(db, ws_uuid, "agent")
    hook_rules = [rule for rule in active_rules if is_hook_applicable_rule(rule)]
    _audit_exception_transitions(db, ws_uuid, audit_use=True)
    version_hash = hashlib.sha256(json.dumps(hook_rules, sort_keys=True).encode()).hexdigest()[:16]
    version = f"{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}-{version_hash}"

    out = PolicySyncOut(
        workspace_id=workspace_id,
        version=version,
        persona="agent",
        fail_mode=getattr(gc, "fail_mode", "fail_open") if gc else "fail_open",
        advisory_mode=getattr(gc, "advisory_mode", False) if gc else False,
        rules=[
            PolicySyncRule(
                rule_id=r["id"],
                match_tool=r.get("match_tool"),
                match_ai_tool=r.get("match_ai_tool"),
                match_pattern=r.get("match_pattern"),
                match_path_pattern=r.get("match_path_pattern"),
                action=r["action"],
                message=r.get("message"),
            )
            for r in hook_rules
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
    _: str = Depends(require_permission("guard.policies.view")),
):
    """List all policies for a workspace — custom rules + active pack rules."""
    ws_uuid = _ws_uuid(workspace_id)
    _audit_exception_transitions(db, ws_uuid, audit_use=False)
    org_ws = _org_ws_subquery(db, workspace_id)

    out: list[PolicyOut] = []

    # Last-hit timestamp per rule_id, aggregated across org workspaces
    last_hits: dict[str, datetime] = dict(
        db.query(GuardAuditEvent.rule_id, func.max(GuardAuditEvent.ts))
        .filter(GuardAuditEvent.workspace_id.in_(org_ws))
        .filter(GuardAuditEvent.rule_id.isnot(None))
        .group_by(GuardAuditEvent.rule_id)
        .all()
    )

    # 1. Custom rules
    customs = (
        db.query(WorkspaceCustomRule)
        .filter(WorkspaceCustomRule.workspace_id.in_(org_ws))
        .order_by(WorkspaceCustomRule.created_at.asc())
        .all()
    )
    out.extend(_custom_to_out(c) for c in customs)

    # 2. Pack rules (with overrides applied)
    installed = (
        db.query(WorkspaceSkillPack)
        .filter(WorkspaceSkillPack.workspace_id.in_(org_ws))
        .order_by(WorkspaceSkillPack.installed_at)
        .all()
    )
    overrides = {
        o.rule_id: o
        for o in db.query(GuardRuleOverride)
        .filter(GuardRuleOverride.workspace_id.in_(org_ws))
        .all()
    }
    seen: set[str] = set()
    for wp in installed:
        pack = _resolve_workspace_pack(db, wp)
        if not pack:
            continue
        for rule in pack.rules or []:
            if rule["id"] in seen:
                continue
            seen.add(rule["id"])
            out.append(_pack_rule_to_out(rule, wp.pack_slug, wp.installed_at, ws_uuid, overrides.get(rule["id"])))

    for p in out:
        p.last_triggered = last_hits.get(p.rule_id)

    return out


@router.get("/coverage", response_model=list[EnforcementCoverageOut])
def get_enforcement_coverage(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.view")),
):
    """Generated enforcement matrix for the workspace's resolved policy sources."""
    return workspace_coverage_matrix(db, _ws_uuid(workspace_id))


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
        "persona_affinity": body.persona_affinity or ["agent", "proxy"],
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


# ── Lint ──────────────────────────────────────────────────────────────────────

class LintIssue(BaseModel):
    rule_id: str
    field: str
    message: str

class LintRequest(BaseModel):
    rules: list[dict]
    fail_mode: Optional[str] = None

class LintResponse(BaseModel):
    errors: list[LintIssue] = []
    warnings: list[LintIssue] = []

_VALID_ACTIONS = set(VALID_ACTIONS)
_VALID_FAIL_MODES = {"fail_open", "fail_closed"}
_MATCH_FIELDS = {"match_tool", "match_pattern", "match_path_pattern", "match_command_word", "match_tokens_before_gt"}


def _lint_rules(rules: list[dict], fail_mode: Optional[str]) -> tuple[list[LintIssue], list[LintIssue]]:
    import re as _re
    errors: list[LintIssue] = []
    warnings: list[LintIssue] = []
    seen_ids: set[str] = set()

    if fail_mode and fail_mode not in _VALID_FAIL_MODES:
        errors.append(LintIssue(rule_id="(policy)", field="fail_mode",
                                message=f"fail_mode must be one of: {', '.join(sorted(_VALID_FAIL_MODES))}"))

    for i, rule in enumerate(rules):
        rid = rule.get("rule_id") or rule.get("id") or f"(rule[{i}])"

        if not rule.get("rule_id") and not rule.get("id"):
            errors.append(LintIssue(rule_id=rid, field="rule_id", message="rule_id is required"))

        if rid in seen_ids:
            errors.append(LintIssue(rule_id=rid, field="rule_id", message=f"Duplicate rule_id '{rid}'"))
        seen_ids.add(rid)

        action = rule.get("action")
        if not action:
            errors.append(LintIssue(rule_id=rid, field="action", message="action is required"))
        elif action not in _VALID_ACTIONS:
            errors.append(LintIssue(rule_id=rid, field="action",
                                    message=f"action '{action}' must be one of: {', '.join(sorted(_VALID_ACTIONS))}"))

        for regex_field in ("match_pattern", "match_path_pattern"):
            val = rule.get(regex_field)
            if val:
                try:
                    _re.compile(val)
                except _re.error as e:
                    errors.append(LintIssue(rule_id=rid, field=regex_field,
                                            message=f"Invalid regex: {e}"))

        if not any(rule.get(f) for f in _MATCH_FIELDS):
            warnings.append(LintIssue(rule_id=rid, field="match_*",
                                      message="No match condition — rule will match every tool call"))

        tokens = rule.get("match_tokens_before_gt")
        if tokens is not None and (not isinstance(tokens, int) or tokens <= 0):
            errors.append(LintIssue(rule_id=rid, field="match_tokens_before_gt",
                                    message="match_tokens_before_gt must be a positive integer"))

    return errors, warnings


@router.post("/lint", response_model=LintResponse)
def lint_policy(
    body: LintRequest,
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.view")),
):
    """Validate a policy (rules list) and return errors + warnings. No DB writes."""
    errors, warnings = _lint_rules(body.rules, body.fail_mode)
    return LintResponse(errors=errors, warnings=warnings)
