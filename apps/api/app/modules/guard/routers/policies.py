"""
ConductGuard — policy engine endpoints.

GET    /guard/policies          — list all team policies (enabled + disabled)
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

from app.core.auth import get_guard_org_id, get_guard_hook_auth
from app.core.database import get_db
from app.modules.guard.models import GuardPolicy, GuardTeam

router = APIRouter(prefix="/guard/policies", tags=["guard-policies"])

_VALID_ACTIONS = {"block", "warn", "audit", "approval", "inject"}

# ── Built-in rule definitions (loaded from YAML) ──────────────────────────────

_POLICIES_FILE = Path(__file__).parent.parent / "builtin_policies.yaml"


def _load_builtin_rules() -> list[dict]:
    with _POLICIES_FILE.open() as f:
        rules = yaml.safe_load(f) or []
    # Normalise: ensure match_pattern and match_path_pattern are present
    for r in rules:
        r.setdefault("match_pattern", None)
        r.setdefault("match_path_pattern", None)
    return rules


_BUILTIN_RULES: list[dict] = _load_builtin_rules()


def seed_builtin_policies(db: Session, team_id) -> None:
    """Insert built-in policies for a team if they do not already exist."""
    for rule in _BUILTIN_RULES:
        exists = (
            db.query(GuardPolicy)
            .filter(GuardPolicy.team_id == team_id, GuardPolicy.rule_id == rule["rule_id"])
            .first()
        )
        if exists:
            continue
        db.add(
            GuardPolicy(
                team_id=team_id,
                builtin=True,
                enabled=True,
                **rule,
            )
        )
    db.commit()


# ── Pydantic schemas ──────────────────────────────────────────────────────────


class PolicyCreate(BaseModel):
    team_id: Optional[str] = None
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
    team_id: str
    rule_id: str
    description: Optional[str] = None
    match_tool: Optional[str] = None
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: str
    message: Optional[str] = None
    enabled: bool
    builtin: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @classmethod
    def model_validate(cls, obj, **kwargs):
        data = {
            "id": str(obj.id),
            "team_id": str(obj.team_id),
            "rule_id": obj.rule_id,
            "description": obj.description,
            "match_tool": obj.match_tool,
            "match_pattern": obj.match_pattern,
            "match_path_pattern": obj.match_path_pattern,
            "action": obj.action,
            "message": obj.message,
            "enabled": obj.enabled,
            "builtin": obj.builtin,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
        }
        return cls(**data)


class PolicySyncRule(BaseModel):
    rule_id: str
    match_tool: Optional[str] = None
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: str
    message: Optional[str] = None


class PolicySyncOut(BaseModel):
    team_id: str
    version: str
    rules: list[PolicySyncRule]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _resolve_team_id(db: Session, team_id: str | None, workspace_id: str | None) -> str:
    """Return a concrete team_id string, or raise 422 if neither param resolves."""
    if team_id:
        return team_id
    if workspace_id:
        from app.modules.guard.routers.teams import _lookup_team
        team = _lookup_team(db, workspace_id)
        if team:
            return str(team.id)
    raise HTTPException(status_code=422, detail="Provide team_id or workspace_id")


def _resolve_team(db: Session, team_id: str) -> GuardTeam:
    """Return GuardTeam by id, 404 if not found."""
    try:
        tid = uuid.UUID(team_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Team not found")
    team = db.query(GuardTeam).filter(GuardTeam.id == tid).first()
    if not team:
        raise HTTPException(status_code=404, detail="No ConductGuard team found")
    return team


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
        team_id=str(p.team_id),
        rule_id=p.rule_id,
        description=p.description,
        match_tool=p.match_tool,
        match_pattern=p.match_pattern,
        match_path_pattern=p.match_path_pattern,
        action=p.action,
        message=p.message,
        enabled=p.enabled,
        builtin=p.builtin,
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
_GENERATE_SYSTEM = (_PROMPTS_DIR / "policy_generate_system.txt").read_text()


class PolicyGenerateRequest(BaseModel):
    prompt: str
    team_id: Optional[str] = None


class PolicyGenerateOut(BaseModel):
    rule_id: str
    description: str
    match_tool: str
    match_pattern: Optional[str] = None
    match_path_pattern: Optional[str] = None
    action: str
    message: str


# Static routes must come before /{id} to avoid path collision.

def _get_anthropic_key(db: Session, team_id: str | None) -> str:
    """Resolve Anthropic API key from the workspace credential vault."""
    import uuid as _uuid
    from app.core.crypto import decrypt
    from app.models.integration import Integration

    if team_id:
        try:
            tid = _uuid.UUID(team_id)
            team = db.query(GuardTeam).filter(GuardTeam.id == tid).first()
            workspace_id = team.conductai_org_id if team else None
        except (ValueError, AttributeError):
            workspace_id = None

        if workspace_id:
            row = (
                db.query(Integration)
                .filter(
                    Integration.workspace_id == workspace_id,
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
    _org_id: str = Depends(get_guard_org_id),
):
    """Use Claude to generate a policy rule from a plain-English description."""
    import json
    import anthropic

    api_key = _get_anthropic_key(db, body.team_id)
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
        # Strip markdown fences if the model wrapped the JSON
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=422, detail="Couldn't generate a rule from that description — try being more specific, e.g. 'block rm -rf in bash' or 'require approval before prod deploys'.")
    except Exception as e:
        raise HTTPException(status_code=502, detail="Rule generation failed — check that your Anthropic API key is valid in Settings → Environments.")

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
    team_id: str = Query(...),
    db: Session = Depends(get_db),
    _auth: str = Depends(get_guard_hook_auth),
):
    """Return the current active ruleset for the hook binary or MCP server."""
    team = _resolve_team(db, team_id)
    active_policies = (
        db.query(GuardPolicy)
        .filter(GuardPolicy.team_id == team.id, GuardPolicy.enabled.is_(True))
        .order_by(GuardPolicy.updated_at.desc())
        .all()
    )

    if active_policies:
        latest_ts = max(p.updated_at for p in active_policies)
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

    return PolicySyncOut(team_id=str(team.id), version=version, rules=rules)


@router.get("", response_model=list[PolicyOut])
def list_policies(
    db: Session = Depends(get_db),
    _org_id: str = Depends(get_guard_org_id),
    team_id: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None),
):
    """Return all team policies."""
    resolved_team_id = _resolve_team_id(db, team_id, workspace_id)
    team = _resolve_team(db, resolved_team_id)

    policies = (
        db.query(GuardPolicy)
        .filter(GuardPolicy.team_id == team.id)
        .order_by(GuardPolicy.builtin.desc(), GuardPolicy.created_at.asc())
        .all()
    )
    return [_policy_to_out(p) for p in policies]


@router.post("", response_model=PolicyOut, status_code=201)
def create_policy(
    body: PolicyCreate,
    db: Session = Depends(get_db),
    _org_id: str = Depends(get_guard_org_id),
):
    """Create a custom (non-builtin) policy rule."""
    if body.action not in _VALID_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action '{body.action}'. Must be one of: {sorted(_VALID_ACTIONS)}",
        )
    if not body.team_id:
        raise HTTPException(status_code=422, detail="team_id is required")
    team = _resolve_team(db, body.team_id)

    policy = GuardPolicy(
        team_id=team.id,
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
    return _policy_to_out(policy)


@router.patch("/{policy_id}", response_model=PolicyOut)
def patch_policy(
    policy_id: str,
    body: PolicyPatch,
    db: Session = Depends(get_db),
    _org_id: str = Depends(get_guard_org_id),
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
    return _policy_to_out(policy)


@router.delete("/{policy_id}", status_code=204)
def delete_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    _org_id: str = Depends(get_guard_org_id),
):
    """Delete a custom policy rule. Built-in rules cannot be deleted."""
    policy = _get_policy_or_404(db, policy_id)

    if policy.builtin:
        raise HTTPException(
            status_code=403,
            detail="Built-in rules cannot be deleted. Disable the rule instead.",
        )

    db.delete(policy)
    db.commit()
