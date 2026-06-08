"""
Secure module — Security Loop for Claude Code

POST   /secure/install                    — install the Security Loop module
DELETE /secure/install                    — uninstall
GET    /secure/installed                  — {installed: bool} — used by CLI
GET    /secure/config                     — full config
PATCH  /secure/config                     — update emit/slack settings
GET    /secure/policies                   — list detection policies
POST   /secure/policies                   — create custom policy
PATCH  /secure/policies/{policy_id}       — update policy
DELETE /secure/policies/{policy_id}       — delete non-builtin policy
"""
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.models.security_config import SecurityConfig, SecurityPolicy

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/secure", tags=["secure"])

_VALID_TYPES = {"injection", "path-traversal", "secret-leak", "auth-bypass", "crypto", "other"}
_VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}

_BUILTIN_POLICIES = [
    ("secret-sk-key",    r"sk-[A-Za-z0-9]{20,}",      "secret-leak",    "high",     "OpenAI/Anthropic API key"),
    ("secret-gh-pat",    r"ghp_[A-Za-z0-9]{36}",      "secret-leak",    "high",     "GitHub Personal Access Token"),
    ("secret-aws-key",   r"AKIA[0-9A-Z]{16}",          "secret-leak",    "critical", "AWS Access Key ID"),
    ("secret-password",  r"password\s*=\s*[^\s]{4,}",  "secret-leak",    "high",     "Hardcoded password"),
    ("secret-api-key",   r"api_?key\s*=\s*[^\s]{4,}",  "secret-leak",    "high",     "Hardcoded API key"),
    ("path-traversal",   r"\.\./\.\./\.\./",            "path-traversal", "medium",   "Path traversal sequence"),
    ("code-eval",        r"\beval\s*\(",                "injection",      "high",     "eval() in code"),
    ("ssl-cert-none",    r"ssl\.CERT_NONE",             "crypto",         "high",     "SSL verification disabled"),
    ("tls-verify-false", r"verify\s*=\s*False",         "crypto",         "medium",   "TLS verification bypassed"),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_builtin_policies(db: Session, workspace_id: str) -> None:
    ws_uuid = uuid.UUID(workspace_id)
    for rule_id, pattern, ftype, severity, description in _BUILTIN_POLICIES:
        existing = db.query(SecurityPolicy).filter(
            SecurityPolicy.workspace_id == ws_uuid,
            SecurityPolicy.rule_id == rule_id,
        ).first()
        if not existing:
            db.add(SecurityPolicy(
                id=uuid.uuid4(),
                workspace_id=ws_uuid,
                rule_id=rule_id,
                description=description,
                pattern=pattern,
                finding_type=ftype,
                severity=severity,
                enabled=True,
                builtin=True,
            ))
    db.commit()


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class InstalledOut(BaseModel):
    installed: bool
    workspace_id: str


class ConfigOut(BaseModel):
    workspace_id: str
    installed: bool
    security_emit_enabled: bool
    security_slack_alerts_enabled: bool
    security_slack_channel: Optional[str]
    slack_integration_id: Optional[UUID] = None
    installed_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ConfigPatch(BaseModel):
    security_emit_enabled: Optional[bool] = None
    security_slack_alerts_enabled: Optional[bool] = None
    security_slack_channel: Optional[str] = None
    slack_integration_id: Optional[UUID] = None


class PolicyOut(BaseModel):
    id: UUID
    workspace_id: UUID
    rule_id: str
    description: Optional[str]
    pattern: Optional[str]
    finding_type: str
    severity: str
    enabled: bool
    builtin: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PolicyIn(BaseModel):
    rule_id: str
    description: Optional[str] = None
    pattern: str
    finding_type: str = "other"
    severity: str = "medium"


class PolicyPatch(BaseModel):
    enabled: Optional[bool] = None
    description: Optional[str] = None
    pattern: Optional[str] = None
    finding_type: Optional[str] = None
    severity: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_config(db: Session, workspace_id: str) -> Optional[SecurityConfig]:
    ws_uuid = uuid.UUID(workspace_id)
    return db.query(SecurityConfig).filter(SecurityConfig.workspace_id == ws_uuid).first()


def _config_to_out(cfg: SecurityConfig) -> ConfigOut:
    return ConfigOut(
        workspace_id=str(cfg.workspace_id),
        installed=cfg.installed,
        security_emit_enabled=cfg.security_emit_enabled,
        security_slack_alerts_enabled=cfg.security_slack_alerts_enabled,
        security_slack_channel=cfg.security_slack_channel,
        slack_integration_id=cfg.slack_integration_id,
        installed_at=cfg.installed_at,
        created_at=cfg.created_at,
        updated_at=cfg.updated_at,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/install", response_model=ConfigOut, status_code=201)
def install(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> ConfigOut:
    """Install the Security Loop module for this workspace."""
    ws_uuid = uuid.UUID(workspace_id)
    cfg = db.query(SecurityConfig).filter(SecurityConfig.workspace_id == ws_uuid).first()
    now = _now()
    if cfg:
        cfg.installed = True
        cfg.installed_at = now
        cfg.updated_at = now
    else:
        cfg = SecurityConfig(
            workspace_id=ws_uuid,
            installed=True,
            security_emit_enabled=True,
            installed_at=now,
            created_at=now,
        )
        db.add(cfg)
    db.commit()
    db.refresh(cfg)
    _seed_builtin_policies(db, workspace_id)
    log.info("secure.installed", workspace_id=workspace_id)
    return _config_to_out(cfg)


@router.delete("/install", status_code=204)
def uninstall(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> None:
    """Uninstall the Security Loop module."""
    cfg = _get_config(db, workspace_id)
    if cfg:
        cfg.installed = False
        cfg.updated_at = _now()
        db.commit()
    log.info("secure.uninstalled", workspace_id=workspace_id)


@router.get("/installed", response_model=InstalledOut)
def get_installed(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
) -> InstalledOut:
    """Return whether the Security Loop module is installed. Used by CLI during login/sync."""
    cfg = _get_config(db, workspace_id)
    return InstalledOut(
        installed=bool(cfg and cfg.installed),
        workspace_id=workspace_id,
    )


@router.get("/config", response_model=ConfigOut)
def get_config(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.activity.view_all")),
) -> ConfigOut:
    cfg = _get_config(db, workspace_id)
    if not cfg:
        raise HTTPException(status_code=404, detail="Security Loop not installed")
    return _config_to_out(cfg)


@router.patch("/config", response_model=ConfigOut)
def patch_config(
    body: ConfigPatch,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> ConfigOut:
    cfg = _get_config(db, workspace_id)
    if not cfg or not cfg.installed:
        raise HTTPException(status_code=404, detail="Security Loop not installed")
    if body.security_emit_enabled is not None:
        cfg.security_emit_enabled = body.security_emit_enabled
    if body.security_slack_alerts_enabled is not None:
        cfg.security_slack_alerts_enabled = body.security_slack_alerts_enabled
    if body.security_slack_channel is not None:
        cfg.security_slack_channel = body.security_slack_channel
    if body.slack_integration_id is not None:
        cfg.slack_integration_id = body.slack_integration_id

    cfg.updated_at = _now()
    db.commit()
    db.refresh(cfg)
    return _config_to_out(cfg)


@router.get("/policies", response_model=list[PolicyOut])
def list_policies(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.activity.view_all")),
) -> list[PolicyOut]:
    ws_uuid = uuid.UUID(workspace_id)
    return db.query(SecurityPolicy).filter(SecurityPolicy.workspace_id == ws_uuid).order_by(
        SecurityPolicy.builtin.desc(), SecurityPolicy.created_at.asc()
    ).all()


@router.post("/policies", response_model=PolicyOut, status_code=201)
def create_policy(
    body: PolicyIn,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.edit")),
) -> PolicyOut:
    if body.finding_type not in _VALID_TYPES:
        raise HTTPException(status_code=422, detail=f"finding_type must be one of: {', '.join(sorted(_VALID_TYPES))}")
    if body.severity not in _VALID_SEVERITIES:
        raise HTTPException(status_code=422, detail=f"severity must be one of: {', '.join(sorted(_VALID_SEVERITIES))}")
    now = _now()
    policy = SecurityPolicy(
        id=uuid.uuid4(),
        workspace_id=uuid.UUID(workspace_id),
        rule_id=body.rule_id,
        description=body.description,
        pattern=body.pattern,
        finding_type=body.finding_type,
        severity=body.severity,
        enabled=True,
        builtin=False,
        created_at=now,
        updated_at=now,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


@router.patch("/policies/{policy_id}", response_model=PolicyOut)
def update_policy(
    policy_id: UUID,
    body: PolicyPatch,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.edit")),
) -> PolicyOut:
    policy = db.query(SecurityPolicy).filter(
        SecurityPolicy.id == policy_id,
        SecurityPolicy.workspace_id == uuid.UUID(workspace_id),
    ).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    if body.enabled is not None:
        policy.enabled = body.enabled
    if not policy.builtin:
        if body.description is not None:
            policy.description = body.description
        if body.pattern is not None:
            policy.pattern = body.pattern
        if body.finding_type is not None:
            if body.finding_type not in _VALID_TYPES:
                raise HTTPException(status_code=422, detail=f"finding_type must be one of: {', '.join(sorted(_VALID_TYPES))}")
            policy.finding_type = body.finding_type
        if body.severity is not None:
            if body.severity not in _VALID_SEVERITIES:
                raise HTTPException(status_code=422, detail=f"severity must be one of: {', '.join(sorted(_VALID_SEVERITIES))}")
            policy.severity = body.severity
    policy.updated_at = _now()
    db.commit()
    db.refresh(policy)
    return policy


@router.delete("/policies/{policy_id}", status_code=204)
def delete_policy(
    policy_id: UUID,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.policies.edit")),
) -> None:
    policy = db.query(SecurityPolicy).filter(
        SecurityPolicy.id == policy_id,
        SecurityPolicy.workspace_id == uuid.UUID(workspace_id),
    ).first()
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    if policy.builtin:
        raise HTTPException(status_code=403, detail="Cannot delete a builtin policy")
    db.delete(policy)
    db.commit()
