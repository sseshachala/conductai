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
    autopilot_enabled: bool = False
    installed_at: Optional[datetime]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class ConfigPatch(BaseModel):
    security_emit_enabled: Optional[bool] = None
    security_slack_alerts_enabled: Optional[bool] = None
    security_slack_channel: Optional[str] = None
    slack_integration_id: Optional[UUID] = None
    autopilot_enabled: Optional[bool] = None


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
        autopilot_enabled=bool(cfg.autopilot_enabled),
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
    """Install the Security Loop module and auto-provision the Security Loop Automation playbook."""
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
    _ensure_security_automation_project(db, workspace_id, install_fix=False)
    log.info("secure.installed", workspace_id=workspace_id)
    return _config_to_out(cfg)


def _get_or_create_security_automation_project(db: Session, ws_uuid: uuid.UUID):
    """Return the permanent Security Automation project, creating it if needed."""
    from app.models.project import Project
    proj = db.query(Project).filter(
        Project.workspace_id == ws_uuid,
        Project.project_type == "security_automation",
    ).first()
    if not proj:
        ws_short = str(ws_uuid).replace("-", "")[:8]
        proj = Project(
            id=uuid.uuid4(),
            workspace_id=ws_uuid,
            name=f"Security Automation · {ws_short}",
            slug=f"security-automation-{ws_short}",
            project_type="security_automation",
            created_at=_now(),
        )
        db.add(proj)
        db.flush()
        log.info("secure.automation_project_created", workspace_id=str(ws_uuid))
    return proj


def _install_workflow_into_project(
    db: Session, ws_uuid: uuid.UUID, project_id: uuid.UUID,
    slug: str, filename: str, display_name: str,
) -> bool:
    """Install a playbook workflow into a project. Idempotent — skips if already installed."""
    from app.models.workflow import Workflow, WorkflowVersion
    from app.models.environment import Environment
    from app.dsl.loader import yaml_to_graph
    from app.dsl.schema import Workflow as DSLWorkflow
    import pathlib, yaml as _yaml

    playbook_path = pathlib.Path(__file__).parent.parent.parent / "playbooks" / filename
    try:
        raw = playbook_path.read_text(encoding="utf-8")
        dsl = DSLWorkflow.model_validate(_yaml.safe_load(raw))
        graph = yaml_to_graph(dsl)
    except Exception as exc:
        log.warning("secure.playbook_load_failed", slug=slug, error=str(exc))
        return False

    existing = db.query(Workflow).filter(
        Workflow.workspace_id == ws_uuid,
        Workflow.project_id == project_id,
        Workflow.playbook_slug == slug,
    ).first()
    if existing:
        # Backfill environment_id if missing
        if not existing.environment_id:
            from app.models.environment import Environment as _Env
            env = (
                db.query(_Env).filter(_Env.workspace_id == ws_uuid, _Env.name == "Default").first()
                or db.query(_Env).filter(_Env.workspace_id == ws_uuid).first()
            )
            if env:
                existing.environment_id = env.id
        # Always update graph so YAML changes take effect without reinstall
        if existing.current_version_id:
            cur_ver = db.query(WorkflowVersion).filter(WorkflowVersion.id == existing.current_version_id).first()
            if cur_ver and cur_ver.graph != graph:
                cur_ver.graph = graph
                log.info("secure.playbook_graph_updated", slug=slug)
        db.commit()
        return False

    # Resolve workspace Default environment
    env = (
        db.query(Environment).filter(Environment.workspace_id == ws_uuid, Environment.name == "Default").first()
        or db.query(Environment).filter(Environment.workspace_id == ws_uuid).first()
    )
    if not env:
        env = Environment(workspace_id=str(ws_uuid), name="Default")
        db.add(env)
        db.flush()

    wf = Workflow(
        id=uuid.uuid4(),
        workspace_id=ws_uuid,
        project_id=project_id,
        name=display_name,
        playbook_slug=slug,
        environment_id=env.id,
        created_at=_now(),
    )
    db.add(wf)
    db.flush()

    ver = WorkflowVersion(
        id=uuid.uuid4(),
        workflow_id=wf.id,
        graph=graph,
        compiled_artifacts={},
        created_at=_now(),
    )
    db.add(ver)
    db.flush()
    wf.current_version_id = ver.id
    db.commit()
    log.info("secure.workflow_installed", slug=slug, project_id=str(project_id))
    return True


def _ensure_security_automation_project(db: Session, workspace_id: str, install_fix: bool = False) -> None:
    """Ensure the Security Automation project exists and has the right workflows installed."""
    ws_uuid = uuid.UUID(workspace_id)
    proj = _get_or_create_security_automation_project(db, ws_uuid)
    _install_workflow_into_project(
        db, ws_uuid, proj.id,
        slug="security_loop",
        filename="security_loop.yaml",
        display_name="Security Loop Automation",
    )
    if install_fix:
        _install_workflow_into_project(
            db, ws_uuid, proj.id,
            slug="security-autopilot-fix",
            filename="security-autopilot-fix.yaml",
            display_name="Security Autopilot Fix",
        )


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
    if body.autopilot_enabled is not None:
        cfg.autopilot_enabled = body.autopilot_enabled
        if body.autopilot_enabled:
            _ensure_security_automation_project(db, workspace_id, install_fix=True)

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
