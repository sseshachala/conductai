"""
ConductGuard — policy engine endpoints.

GET    /guard/policies          — list all team policies (enabled + disabled)
POST   /guard/policies          — create custom rule
PATCH  /guard/policies/{id}     — update rule (enable/disable/edit)
DELETE /guard/policies/{id}     — delete custom rule (builtin=True rules cannot be deleted)
GET    /guard/policies/sync     — returns current active ruleset as JSON (polled by hook binary every 60s)
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_workspace_role
from app.core.database import get_db
from app.modules.guard.models import GuardPolicy, GuardTeam

router = APIRouter(prefix="/guard/policies", tags=["guard-policies"])

_VALID_ACTIONS = {"block", "warn", "audit", "approval", "inject"}

# ── Built-in rule definitions ─────────────────────────────────────────────────

_BUILTIN_RULES: list[dict] = [
    {
        "rule_id": "no-rm-rf",
        "description": "Block recursive deletes",
        "match_tool": "bash",
        "match_pattern": r"rm\s+-rf",
        "match_path_pattern": None,
        "action": "block",
        "message": "Recursive delete blocked. Delete files individually.",
    },
    {
        "rule_id": "no-drop-table",
        "description": "Block DROP TABLE statements",
        "match_tool": "bash,edit,write",
        "match_pattern": r"DROP\s+TABLE",
        "match_path_pattern": None,
        "action": "block",
        "message": "DROP TABLE blocked. Use a migration with rollback.",
    },
    {
        "rule_id": "no-env-commits",
        "description": "Block committing .env files",
        "match_tool": "bash",
        "match_pattern": r"git (add|commit).+\.env",
        "match_path_pattern": None,
        "action": "block",
        "message": ".env files must not be committed.",
    },
    {
        "rule_id": "no-hardcoded-secrets",
        "description": "Warn on possible hardcoded secrets",
        "match_tool": "edit,write",
        "match_pattern": r"(API_KEY|SECRET|PASSWORD|TOKEN)\s*=\s*['\"][A-Za-z0-9+/]{16,}",
        "match_path_pattern": None,
        "action": "warn",
        "message": "Possible hardcoded secret. Use environment variables.",
    },
    {
        "rule_id": "approve-prod-deploy",
        "description": "Require approval for production deploys",
        "match_tool": "bash",
        "match_pattern": r"deploy.*(prod|production)|vercel.*--prod|railway.*prod",
        "match_path_pattern": None,
        "action": "approval",
        "message": "Production deploy requested. Approve?",
    },
    {
        "rule_id": "approve-db-migration-prod",
        "description": "Require approval for production DB migrations",
        "match_tool": "bash",
        "match_pattern": r"alembic upgrade|prisma migrate deploy",
        "match_path_pattern": None,
        "action": "approval",
        "message": "DB migration in production. Approve?",
    },
    {
        "rule_id": "audit-migrations",
        "description": "Audit migration file modifications",
        "match_tool": "edit,write",
        "match_pattern": None,
        "match_path_pattern": r"alembic/versions/.*\.py$",
        "action": "audit",
        "message": "Migration file modified",
    },
    {
        "rule_id": "audit-ci-config",
        "description": "Audit CI config modifications",
        "match_tool": "edit,write",
        "match_pattern": None,
        "match_path_pattern": r"\.github/workflows/.*",
        "action": "audit",
        "message": "CI config modified",
    },
]


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


def _get_team_for_workspace(db: Session, workspace_id: str) -> GuardTeam:
    """Return the GuardTeam bound to this workspace, 404 if none."""
    team = (
        db.query(GuardTeam)
        .filter(GuardTeam.conductai_workspace_id == workspace_id)
        .first()
    )
    if not team:
        raise HTTPException(status_code=404, detail="No ConductGuard team found for this workspace.")
    return team


def _get_policy(db: Session, policy_id: str, team_id) -> GuardPolicy:
    """Return a GuardPolicy by id scoped to team, 404 if not found."""
    policy = (
        db.query(GuardPolicy)
        .filter(GuardPolicy.id == policy_id, GuardPolicy.team_id == team_id)
        .first()
    )
    if not policy:
        raise HTTPException(status_code=404, detail=f"Policy '{policy_id}' not found.")
    return policy


# ── Endpoints ─────────────────────────────────────────────────────────────────


# Static route must come before /{id} to avoid path collision.
@router.get("/sync", response_model=PolicySyncOut)
def sync_policies(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """
    Return the current active ruleset for the hook binary.
    Only enabled=True rules are included.
    version is the latest updated_at timestamp across all active rules.
    Polled by the hook binary every 60 seconds.
    """
    team = _get_team_for_workspace(db, workspace_id)

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

    return PolicySyncOut(
        team_id=str(team.id),
        version=version,
        rules=rules,
    )


@router.get("", response_model=list[PolicyOut])
def list_policies(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin", "editor", "viewer")),
):
    """Return all team policies (enabled and disabled)."""
    team = _get_team_for_workspace(db, workspace_id)
    return (
        db.query(GuardPolicy)
        .filter(GuardPolicy.team_id == team.id)
        .order_by(GuardPolicy.builtin.desc(), GuardPolicy.created_at.asc())
        .all()
    )


@router.post("", response_model=PolicyOut, status_code=201)
def create_policy(
    body: PolicyCreate,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """Create a custom (non-builtin) policy rule."""
    if body.action not in _VALID_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action '{body.action}'. Must be one of: {sorted(_VALID_ACTIONS)}",
        )
    team = _get_team_for_workspace(db, workspace_id)

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
    return policy


@router.patch("/{policy_id}", response_model=PolicyOut)
def patch_policy(
    policy_id: str,
    body: PolicyPatch,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """Update a policy rule (enable/disable/edit). Works on both builtin and custom rules."""
    if body.action is not None and body.action not in _VALID_ACTIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid action '{body.action}'. Must be one of: {sorted(_VALID_ACTIONS)}",
        )
    team = _get_team_for_workspace(db, workspace_id)
    policy = _get_policy(db, policy_id, team.id)

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
    return policy


@router.delete("/{policy_id}", status_code=204)
def delete_policy(
    policy_id: str,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _role: str = Depends(require_workspace_role("admin")),
):
    """Delete a custom policy rule. Built-in rules cannot be deleted."""
    team = _get_team_for_workspace(db, workspace_id)
    policy = _get_policy(db, policy_id, team.id)

    if policy.builtin:
        raise HTTPException(
            status_code=403,
            detail="Built-in rules cannot be deleted. Disable the rule instead.",
        )

    db.delete(policy)
    db.commit()
