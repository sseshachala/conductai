"""
Guard workspace config endpoints.

GET   /guard/config?workspace_id          — get config (creates if not exists)
PATCH /guard/config?workspace_id          — update alert_channel, notify_on_block, notify_on_budget
GET   /guard/config/installed?workspace_id — returns {installed, workspace_id, invite_code}
"""
import secrets
import uuid
from datetime import datetime, timezone

import structlog

log = structlog.get_logger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, get_user_id, require_workspace_role, require_permission
from app.core.database import get_db
from app.modules.guard.models import GuardConfig, GuardMemberConfig, WorkspaceSkillPack

router = APIRouter(prefix="/guard/config", tags=["guard-config"])


# ── Pydantic models ────────────────────────────────────────────────────────────

_VALID_ENFORCEMENT_MODES = {"block", "warn", "audit"}


class ConfigOut(BaseModel):
    workspace_id: str
    invite_code: str
    slug: str | None
    alert_channel: str | None
    alert_slack_integration_id: str | None
    enforcement_mode: str
    notify_on_block: bool
    notify_on_budget: bool
    automation_security_scan: bool = False
    automation_workflow_trigger: bool = False
    created_at: datetime
    updated_at: datetime | None
    automation_warnings: list[str] = []

    class Config:
        from_attributes = True


class ConfigPatch(BaseModel):
    alert_channel: str | None = None
    alert_slack_integration_id: str | None = None
    enforcement_mode: str | None = None
    notify_on_block: bool | None = None
    notify_on_budget: bool | None = None
    automation_security_scan: bool | None = None
    automation_workflow_trigger: bool | None = None


class InstallStatusOut(BaseModel):
    installed: bool
    workspace_id: str | None = None
    invite_code: str | None = None
    member_token: str | None = None
    user_email: str | None = None
    clerk_user_id: str | None = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_or_create_config(db: Session, workspace_id: str) -> GuardConfig:
    """Return existing GuardConfig or create one (with seeded policies)."""
    ws_uuid = uuid.UUID(workspace_id)
    config = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    if config:
        return config

    config = GuardConfig(
        workspace_id=ws_uuid,
        invite_code=secrets.token_hex(16),
    )
    db.add(config)
    db.flush()
    # Auto-install conduct-base for new workspaces
    existing = db.get(WorkspaceSkillPack, (ws_uuid, "conduct-base"))
    if not existing:
        db.add(WorkspaceSkillPack(workspace_id=ws_uuid, pack_slug="conduct-base", installed_by="system:onboard"))
    db.commit()
    db.refresh(config)
    log.info("guard.config_created", workspace_id=workspace_id)
    return config


def _config_to_out(cfg: GuardConfig) -> ConfigOut:
    return ConfigOut(
        workspace_id=str(cfg.workspace_id),
        invite_code=cfg.invite_code,
        slug=cfg.slug,
        alert_channel=cfg.alert_channel,
        alert_slack_integration_id=str(cfg.alert_slack_integration_id) if cfg.alert_slack_integration_id else None,
        enforcement_mode=cfg.enforcement_mode,
        notify_on_block=cfg.notify_on_block,
        notify_on_budget=cfg.notify_on_budget,
        automation_security_scan=bool(cfg.automation_security_scan),
        automation_workflow_trigger=bool(cfg.automation_workflow_trigger),
        created_at=cfg.created_at,
        updated_at=cfg.updated_at,
    )


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/installed", response_model=InstallStatusOut)
def get_install_status(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
):
    """Return whether Guard is installed for the workspace.
    Auto-provisions a guard_member_config entry for the calling user if they are
    a workspace member (idempotent).
    """
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return InstallStatusOut(installed=False)

    config = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    if not config:
        return InstallStatusOut(installed=False)

    # Idempotent member provisioning — never blocks the response
    try:
        from sqlalchemy import text
        existing = db.execute(
            text("""
                SELECT 1 FROM guard_member_config
                WHERE workspace_id = :ws AND clerk_user_id = :uid
                LIMIT 1
            """),
            {"ws": workspace_id, "uid": user_id},
        ).fetchone()
        if not existing:
            db.execute(
                text("""
                    INSERT INTO guard_member_config (workspace_id, clerk_user_id, member_token, active, joined_at)
                    VALUES (:ws, :uid, :token, true, :now)
                    ON CONFLICT (workspace_id, clerk_user_id) DO NOTHING
                """),
                {
                    "ws": workspace_id,
                    "uid": user_id,
                    "token": secrets.token_hex(32),
                    "now": datetime.now(timezone.utc),
                },
            )
            db.commit()
            log.info("guard.member_provisioned", workspace_id=workspace_id, user_id=user_id)
    except Exception:
        db.rollback()  # non-fatal

    # Fetch member_token for the calling user so CLI can use it
    token_row = db.execute(
        text("SELECT member_token FROM guard_member_config WHERE workspace_id = :ws AND clerk_user_id = :uid LIMIT 1"),
        {"ws": workspace_id, "uid": user_id},
    ).fetchone()

    from app.core.auth import get_clerk_user_email as _get_email
    user_email = _get_email(user_id)
    return InstallStatusOut(
        installed=True,
        workspace_id=workspace_id,
        invite_code=config.invite_code,
        member_token=token_row.member_token if token_row else None,
        user_email=user_email,
        clerk_user_id=user_id,
    )


@router.get("", response_model=ConfigOut)
def get_config(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Return Guard config for the workspace, creating it if it does not yet exist."""
    config = _get_or_create_config(db, workspace_id)
    return _config_to_out(config)


@router.patch("", response_model=ConfigOut)
def patch_config(
    body: ConfigPatch,
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Update Guard notification/channel settings for the workspace."""
    from fastapi import HTTPException
    config = _get_or_create_config(db, workspace_id)
    if body.alert_channel is not None:
        config.alert_channel = body.alert_channel
    if body.alert_slack_integration_id is not None:
        import uuid as _uuid
        config.alert_slack_integration_id = _uuid.UUID(body.alert_slack_integration_id) if body.alert_slack_integration_id else None
    if body.enforcement_mode is not None:
        if body.enforcement_mode not in _VALID_ENFORCEMENT_MODES:
            raise HTTPException(
                status_code=422,
                detail=f"enforcement_mode must be one of: {', '.join(sorted(_VALID_ENFORCEMENT_MODES))}",
            )
        config.enforcement_mode = body.enforcement_mode
    if body.notify_on_block is not None:
        config.notify_on_block = body.notify_on_block
    if body.notify_on_budget is not None:
        config.notify_on_budget = body.notify_on_budget
    if body.automation_security_scan is not None:
        config.automation_security_scan = body.automation_security_scan
    if body.automation_workflow_trigger is not None:
        config.automation_workflow_trigger = body.automation_workflow_trigger
    config.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(config)

    out = _config_to_out(config)
    return out


@router.delete("", status_code=204)
def delete_config(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Uninstall Guard for the workspace — removes guard_config and all guard_member_config rows."""
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return
    db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).delete()
    db.query(GuardMemberConfig).filter(GuardMemberConfig.workspace_id == ws_uuid).delete()
    db.commit()
    log.info("guard.config_deleted", workspace_id=workspace_id)


class ResyncOut(BaseModel):
    ok: bool
    resync_requested_at: str


_VALID_PERSONAS = {"conservative", "standard", "developer"}


class PersonaOut(BaseModel):
    persona: str          # active persona for the calling user
    assigned_by: str      # 'user' or 'admin'
    workspace_default: str


class PersonaPatch(BaseModel):
    persona: str
    developer_id: str | None = None   # if set, override for that member only; else workspace default


@router.get("/persona", response_model=PersonaOut)
def get_persona(
    workspace_id: str = Depends(get_workspace_id),
    user_id: str = Depends(get_user_id),
    db: Session = Depends(get_db),
):
    """Return the active persona for the calling user.
    Resolves: member override → workspace default → 'standard'.
    """
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")

    cfg = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    workspace_default = (cfg.persona if cfg and cfg.persona else "standard")

    member = (
        db.query(GuardMemberConfig)
        .filter(
            GuardMemberConfig.workspace_id == ws_uuid,
            GuardMemberConfig.clerk_user_id == user_id,
        )
        .first()
    )

    if member and member.persona:
        return PersonaOut(
            persona=member.persona,
            assigned_by=member.assigned_by or "user",
            workspace_default=workspace_default,
        )

    return PersonaOut(
        persona=workspace_default,
        assigned_by="user",
        workspace_default=workspace_default,
    )


@router.patch("/persona", response_model=PersonaOut)
def set_persona(
    body: PersonaPatch,
    workspace_id: str = Depends(get_workspace_id),
    _: str = Depends(require_permission("guard.settings.edit")),
    db: Session = Depends(get_db),
):
    """Admin sets the persona for the workspace or a specific developer.

    - No developer_id → sets workspace default for all members
    - developer_id → sets per-member override (assigned_by: admin, locked)
    """
    if body.persona not in _VALID_PERSONAS:
        raise HTTPException(status_code=422, detail=f"persona must be one of {sorted(_VALID_PERSONAS)}")

    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")

    if body.developer_id:
        # Per-member override — admin-locked
        member = (
            db.query(GuardMemberConfig)
            .filter(
                GuardMemberConfig.workspace_id == ws_uuid,
                GuardMemberConfig.clerk_user_id == body.developer_id,
            )
            .first()
        )
        if not member:
            raise HTTPException(status_code=404, detail="Developer not in this workspace")
        member.persona = body.persona
        member.assigned_by = "admin"
        db.commit()
        log.info("guard.persona_set_member", workspace_id=workspace_id, developer_id=body.developer_id, persona=body.persona)
        cfg = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
        workspace_default = cfg.persona if cfg else "standard"
        return PersonaOut(persona=body.persona, assigned_by="admin", workspace_default=workspace_default)

    # Workspace-wide default
    cfg = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    if not cfg:
        raise HTTPException(status_code=404, detail="Guard not installed for this workspace")
    cfg.persona = body.persona
    db.commit()
    log.info("guard.persona_set_workspace", workspace_id=workspace_id, persona=body.persona)
    return PersonaOut(persona=body.persona, assigned_by="admin", workspace_default=body.persona)


@router.post("/resync", response_model=ResyncOut, status_code=200)
def request_resync(
    workspace_id: str = Query(...),
    db: Session = Depends(get_db),
    _role: str = Depends(require_workspace_role("admin", "developer")),
):
    """Bump resync_requested_at so the CLI detects a version change within its next 60s poll."""
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid workspace_id")
    config = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    if not config:
        raise HTTPException(status_code=404, detail="Guard not installed")
    config.resync_requested_at = datetime.now(timezone.utc)
    db.commit()
    log.info("guard.resync_requested", workspace_id=workspace_id)
    return ResyncOut(ok=True, resync_requested_at=config.resync_requested_at.isoformat())


class JoinIn(BaseModel):
    invite_code: str
    email: str


class JoinOut(BaseModel):
    workspace_id: str
    member_token: str
    policy: dict


# Standalone router so this doesn't need /guard/config prefix
join_router = APIRouter(prefix="/guard", tags=["guard-config"])


@join_router.post("/join", response_model=JoinOut)
def join_guard(body: JoinIn, db: Session = Depends(get_db)):
    """Developer joins Guard via invite code. Returns workspace_id + member_token + policy."""
    import uuid
    config = db.query(GuardConfig).filter(GuardConfig.invite_code == body.invite_code).first()
    if not config:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Invalid invite code")

    workspace_id = str(config.workspace_id)

    # Upsert guard_member_config keyed on (workspace_id, email)
    from sqlalchemy import text
    existing = db.execute(
        text("""
            SELECT member_token FROM guard_member_config
            WHERE workspace_id = :ws AND clerk_user_id = :email
            LIMIT 1
        """),
        {"ws": workspace_id, "email": body.email},
    ).fetchone()

    if existing:
        member_token = existing.member_token
    else:
        member_token = secrets.token_hex(32)
        db.execute(
            text("""
                INSERT INTO guard_member_config (workspace_id, clerk_user_id, member_token, active, joined_at)
                VALUES (:ws, :email, :token, true, :now)
                ON CONFLICT (workspace_id, clerk_user_id) DO NOTHING
            """),
            {
                "ws": workspace_id,
                "email": body.email,
                "token": member_token,
                "now": datetime.now(timezone.utc),
            },
        )
        db.commit()
        log.info("guard.developer_joined", workspace_id=workspace_id, email=body.email)

    # Fetch policies for this workspace
    from app.modules.guard.models import GuardPolicy
    policies_rows = db.query(GuardPolicy).filter(
        GuardPolicy.workspace_id == config.workspace_id,
        GuardPolicy.enabled == True,
    ).all()

    rules = [
        {
            "rule_id":           str(p.id),
            "match_tool":        p.match_tool or "*",
            "match_pattern":     p.match_pattern,
            "match_path_pattern": p.match_path_pattern,
            "action":            p.action,
            "message":           p.rule_message,
        }
        for p in policies_rows
    ]
    policy = {"workspace_id": workspace_id, "version": "1", "rules": rules}

    return JoinOut(workspace_id=workspace_id, member_token=member_token, policy=policy)


class InviteRegenOut(BaseModel):
    invite_code: str


@router.post("/invite/regenerate", response_model=InviteRegenOut)
def regenerate_invite(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Generate a new invite code for the workspace Guard config."""
    config = _get_or_create_config(db, workspace_id)
    config.invite_code = secrets.token_hex(16)
    config.updated_at = datetime.now(timezone.utc)
    db.commit()
    log.info("guard.invite_regenerated", workspace_id=workspace_id)
    return InviteRegenOut(invite_code=config.invite_code)
