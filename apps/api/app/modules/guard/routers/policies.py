"""
ConductGuard — policy engine endpoints.

GET    /guard/policies          — list all workspace policies (enabled + disabled)
POST   /guard/policies          — create custom rule
PATCH  /guard/policies/{id}     — update rule (enable/disable/edit)
DELETE /guard/policies/{id}     — delete custom rule (builtin=True rules cannot be deleted)
GET    /guard/policies/sync     — returns current active ruleset as JSON (polled by hook binary every 60s)
"""
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, get_guard_hook_auth
from app.core.database import get_db
from app.modules.guard.models import GuardAuditEvent, GuardConfig as _GuardConfig, GuardPolicy

router = APIRouter(prefix="/guard/policies", tags=["guard-policies"])

_VALID_ACTIONS = {"block", "warn", "audit", "approval", "inject"}

# ── Built-in rule definitions (loaded from YAML) ──────────────────────────────

_POLICIES_FILE = Path(__file__).parent.parent / "builtin_policies.yaml"


def _load_builtin_rules() -> list[dict]:
    with _POLICIES_FILE.open() as f:
        rules = yaml.safe_load(f) or []
    for r in rules:
        r.setdefault("match_pattern", None)
        r.setdefault("match_path_pattern", None)
    return rules


_BUILTIN_RULES: list[dict] = _load_builtin_rules()


def auto_seed_if_changed(db: Session) -> None:
    """On startup: if builtin_policies.yaml has changed since last run, upsert
    policies for every workspace that has Guard enabled (has a GuardConfig row).

    Checksum is persisted to builtin_policies.yaml.sha256 next to the YAML file.
    Non-fatal: any exception is swallowed so startup is never blocked.
    """
    import hashlib
    _CHECKSUM_FILE = _POLICIES_FILE.with_suffix(".yaml.sha256")

    try:
        content = _POLICIES_FILE.read_bytes()
        current_sha = hashlib.sha256(content).hexdigest()

        stored_sha = _CHECKSUM_FILE.read_text().strip() if _CHECKSUM_FILE.exists() else ""
        if current_sha == stored_sha:
            return  # YAML unchanged — nothing to do

        # YAML changed (or first run): upsert for all Guard-enabled workspaces
        from app.modules.guard.models import GuardConfig as _GC
        workspace_ids = [row.workspace_id for row in db.query(_GC.workspace_id).all()]

        rules = _load_builtin_rules()
        for ws_id in workspace_ids:
            ws_uuid = uuid.UUID(str(ws_id))
            added = updated = 0
            for rule in rules:
                rule_data = {**rule, "description": (rule.get("description") or "")[:255]}
                existing = (
                    db.query(GuardPolicy)
                    .filter(GuardPolicy.workspace_id == ws_uuid, GuardPolicy.rule_id == rule_data["rule_id"])
                    .first()
                )
                if existing is None:
                    db.add(GuardPolicy(workspace_id=ws_uuid, builtin=True, enabled=True, **rule_data))
                    added += 1
                else:
                    existing.description = rule_data.get("description", existing.description)
                    existing.match_pattern = rule_data.get("match_pattern")
                    existing.match_path_pattern = rule_data.get("match_path_pattern")
                    existing.action = rule_data.get("action", existing.action)
                    existing.message = rule_data.get("message", existing.message)
                    if "match_tokens_before_gt" in rule_data:
                        existing.match_tokens_before_gt = rule_data["match_tokens_before_gt"]
                    existing.updated_at = datetime.now(timezone.utc)
                    updated += 1
            db.commit()
            import structlog as _sl
            _sl.get_logger(__name__).info(
                "guard.builtin_policies_seeded",
                workspace_id=str(ws_id),
                added=added,
                updated=updated,
            )

        # Persist new checksum so next startup is a no-op
        _CHECKSUM_FILE.write_text(current_sha)

    except Exception as exc:
        import structlog as _sl
        _sl.get_logger(__name__).warning("guard.auto_seed_failed", error=str(exc))


def seed_builtin_policies(db: Session, workspace_id) -> None:
    """Insert built-in policies for a workspace if they do not already exist."""
    ws_uuid = uuid.UUID(str(workspace_id))
    for rule in _BUILTIN_RULES:
        exists = (
            db.query(GuardPolicy)
            .filter(GuardPolicy.workspace_id == ws_uuid, GuardPolicy.rule_id == rule["rule_id"])
            .first()
        )
        if exists:
            continue
        db.add(
            GuardPolicy(
                workspace_id=ws_uuid,
                builtin=True,
                enabled=True,
                **rule,
            )
        )
    db.commit()


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class PolicyCreate(BaseModel):
    workspace_id: Optional[str] = None
    rule_id: str
    description: Optional[str] = None
    match_tool: Optional[str] = None
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: str
    message: Optional[str] = None


class PolicyPatch(BaseModel):
    enabled: Optional[bool] = None
    description: Optional[str] = None
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: Optional[str] = None
    message: Optional[str] = None


class PolicyOut(BaseModel):
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
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


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
    rules: list[PolicySyncRule]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_policy_audit(db: Session, workspace_id: uuid.UUID, tool_call: str, p: GuardPolicy) -> None:
    """Write a GuardAuditEvent row for admin policy mutations. Non-fatal."""
    try:
        summary = f"rule_id={p.rule_id} action={p.action} enabled={p.enabled}"[:500]
        db.add(GuardAuditEvent(
            workspace_id=workspace_id,
            clerk_user_id=None,
            ai_tool="platform",
            tool_call=tool_call,
            decision="allowed",
            rule_id=p.rule_id,
            input_summary=summary,
            ts=datetime.now(timezone.utc),
        ))
        db.commit()
    except Exception as exc:
        import structlog as _sl
        _sl.get_logger(__name__).warning("guard.policy_audit_write_failed", exc=str(exc))


def _get_policy_or_404(db: Session, policy_id: str) -> GuardPolicy:
    try:
        pid = uuid.UUID(policy_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Policy not found")
    policy = db.query(GuardPolicy).filter(GuardPolicy.id == pid).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


def _policy_to_out(p: GuardPolicy) -> PolicyOut:
    return PolicyOut(
        id=str(p.id),
        workspace_id=str(p.workspace_id),
        rule_id=p.rule_id,
        description=p.description,
        match_tool=p.match_tool,
        match_pattern=p.match_pattern,
        match_path_pattern=p.match_path_pattern,
        action=p.action,
        message=p.message,
        enabled=p.enabled,
        builtin=p.builtin,
        pack_id=p.pack_id,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_GENERATE_SYSTEM = (_PROMPTS_DIR / "policy_generate_system.txt").read_text()


class PolicyGenerateRequest(BaseModel):
    prompt: str
    workspace_id: Optional[str] = None


class PolicyGenerateOut(BaseModel):
    rule_id: str
    description: str
    match_tool: str
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: str
    message: str


def _get_anthropic_key(db: Session, workspace_id: str | None) -> str:
    """Resolve Anthropic API key from the workspace credential vault."""
    from app.core.crypto import decrypt
    from app.models.integration import Integration

    if workspace_id:
        try:
            ws_uuid = uuid.UUID(workspace_id)
        except ValueError:
            ws_uuid = None

        if ws_uuid:
            row = (
                db.query(Integration)
                .filter(
                    Integration.workspace_id == ws_uuid,
                    Integration.handle == "anthropic",
                )
                .first()
            )
            if row and row.encrypted_credentials:
                creds = decrypt(row.encrypted_credentials)
                key = creds.get("api_key", "")
                if key:
                    return key

    from app.core.config import settings
    return settings.anthropic_api_key


@router.post("/generate", response_model=PolicyGenerateOut)
def generate_policy(
    body: PolicyGenerateRequest,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Use Claude to generate a policy rule from a plain-English description."""
    import json
    import anthropic

    resolved_ws = body.workspace_id or workspace_id
    api_key = _get_anthropic_key(db, resolved_ws)
    if not api_key:
        raise HTTPException(status_code=503, detail="Anthropic API key not configured — add it in Settings → Environments")

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
            detail="Couldn't generate a rule from that description — try being more specific.",
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Rule generation failed — check that your Anthropic API key is valid in Settings → Environments.",
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
    """Return the current active ruleset for the hook binary or MCP server."""
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")

    active_policies = (
        db.query(GuardPolicy)
        .filter(GuardPolicy.workspace_id == ws_uuid, GuardPolicy.enabled.is_(True), GuardPolicy.archived_at.is_(None))
        .order_by(GuardPolicy.updated_at.desc())
        .all()
    )

    if active_policies:
        latest_ts = max(p.updated_at for p in active_policies)
    else:
        latest_ts = None

    gc = db.query(_GuardConfig).filter(_GuardConfig.workspace_id == ws_uuid).first()
    if gc and gc.resync_requested_at:
        resync_ts = gc.resync_requested_at if gc.resync_requested_at.tzinfo is not None \
            else gc.resync_requested_at.replace(tzinfo=timezone.utc)
        if latest_ts is not None:
            latest_ts = max(latest_ts, resync_ts)
        else:
            latest_ts = resync_ts

    if latest_ts is not None:
        version = latest_ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        version = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    rules = [
        PolicySyncRule(
            rule_id=p.rule_id,
            match_tool=p.match_tool,
            match_pattern=p.match_pattern,
            match_path_pattern=p.match_path_pattern,
            action=p.action,
            message=p.message,
        )
        for p in active_policies
    ]

    return PolicySyncOut(workspace_id=workspace_id, version=version, rules=rules)


@router.get("", response_model=list[PolicyOut])
def list_policies(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Return all workspace policies."""
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")

    policies = (
        db.query(GuardPolicy)
        .filter(GuardPolicy.workspace_id == ws_uuid, GuardPolicy.archived_at.is_(None))
        .order_by(GuardPolicy.builtin.desc(), GuardPolicy.created_at.asc())
        .all()
    )
    return [_policy_to_out(p) for p in policies]


@router.post("", response_model=PolicyOut, status_code=201)
def create_policy(
    body: PolicyCreate,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Create a custom (non-builtin) policy rule."""
    if body.action not in _VALID_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action '{body.action}'. Must be one of: {sorted(_VALID_ACTIONS)}",
        )

    resolved_ws = body.workspace_id or workspace_id
    try:
        ws_uuid = uuid.UUID(resolved_ws)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")

    policy = GuardPolicy(
        workspace_id=ws_uuid,
        rule_id=body.rule_id,
        description=body.description,
        match_tool=body.match_tool,
        match_pattern=body.match_pattern,
        match_path_pattern=body.match_path_pattern,
        action=body.action,
        message=body.message,
        enabled=True,
        builtin=False,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    _write_policy_audit(db, ws_uuid, "policy_created", policy)
    return _policy_to_out(policy)


@router.patch("/{policy_id}", response_model=PolicyOut)
def patch_policy(
    policy_id: str,
    body: PolicyPatch,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Update a policy rule (enable/disable/edit). Works on both builtin and custom rules."""
    if body.action is not None and body.action not in _VALID_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action '{body.action}'. Must be one of: {sorted(_VALID_ACTIONS)}",
        )
    policy = _get_policy_or_404(db, policy_id)

    if body.enabled is not None:
        policy.enabled = body.enabled
    if body.description is not None:
        policy.description = body.description
    if body.match_pattern is not None:
        policy.match_pattern = body.match_pattern
    if body.match_path_pattern is not None:
        policy.match_path_pattern = body.match_path_pattern
    if body.action is not None:
        policy.action = body.action
    if body.message is not None:
        policy.message = body.message

    policy.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(policy)
    _write_policy_audit(db, policy.workspace_id, "policy_updated", policy)
    return _policy_to_out(policy)


@router.delete("/{policy_id}", status_code=204)
def delete_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Delete a custom policy rule. Built-in rules cannot be deleted."""
    policy = _get_policy_or_404(db, policy_id)

    if policy.builtin:
        raise HTTPException(
            status_code=403,
            detail="Built-in rules cannot be deleted. Disable the rule instead.",
        )

    from datetime import datetime, timezone as _tz
    policy.archived_at = datetime.now(_tz.utc)
    db.commit()
    _write_policy_audit(db, policy.workspace_id, "policy_archived", policy)


@router.post("/refresh-builtins")
def refresh_builtins(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Upsert all built-in policies from builtin_policies.yaml into the workspace.

    - New rules (not yet in DB) are inserted enabled=True.
    - Existing rules have description, match_pattern, match_path_pattern, action,
      message, and match_tokens_before_gt refreshed from YAML.
    - User-toggled enabled state is preserved.
    """
    ws_uuid = uuid.UUID(str(workspace_id))
    added = updated = 0
    for rule in _BUILTIN_RULES:
        # description column is String(255) — truncate long YAML descriptions
        rule = {**rule, "description": (rule.get("description") or "")[:255]}
        existing = (
            db.query(GuardPolicy)
            .filter(GuardPolicy.workspace_id == ws_uuid, GuardPolicy.rule_id == rule["rule_id"])
            .first()
        )
        if existing is None:
            db.add(GuardPolicy(workspace_id=ws_uuid, builtin=True, enabled=True, **rule))
            added += 1
        else:
            existing.description = rule.get("description", existing.description)
            existing.match_pattern = rule.get("match_pattern")
            existing.match_path_pattern = rule.get("match_path_pattern")
            existing.action = rule.get("action", existing.action)
            existing.message = rule.get("message", existing.message)
            if "match_tokens_before_gt" in rule:
                existing.match_tokens_before_gt = rule["match_tokens_before_gt"]
            existing.updated_at = datetime.now(timezone.utc)
            updated += 1
    db.commit()
    return {"added": added, "updated": updated, "total": added + updated}
