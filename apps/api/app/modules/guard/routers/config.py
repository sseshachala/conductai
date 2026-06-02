"""
Guard workspace config endpoints.

GET   /guard/config?workspace_id          — get config (creates if not exists)
PATCH /guard/config?workspace_id          — update alert_channel, notify_on_block, notify_on_budget
GET   /guard/config/installed?workspace_id — returns {installed, workspace_id, invite_code}
"""
import secrets
from datetime import datetime, timezone

import structlog

log = structlog.get_logger(__name__)

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, get_user_id
from app.core.database import get_db
from app.modules.guard.models import GuardConfig, GuardMemberConfig
from app.modules.guard.routers.policies import seed_builtin_policies

router = APIRouter(prefix="/guard/config", tags=["guard-config"])


# ── Pydantic models ────────────────────────────────────────────────────────────

class ConfigOut(BaseModel):
    workspace_id: str
    invite_code: str
    slug: str | None
    alert_channel: str | None
    notify_on_block: bool
    notify_on_budget: bool
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True


class ConfigPatch(BaseModel):
    alert_channel: str | None = None
    notify_on_block: bool | None = None
    notify_on_budget: bool | None = None


class InstallStatusOut(BaseModel):
    installed: bool
    workspace_id: str | None = None
    invite_code: str | None = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_or_create_config(db: Session, workspace_id: str) -> GuardConfig:
    """Return existing GuardConfig or create one (with seeded policies)."""
    import uuid
    ws_uuid = uuid.UUID(workspace_id)
    config = db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).first()
    if config:
        return config

    config = GuardConfig(
        workspace_id=ws_uuid,
        invite_code=secrets.token_hex(16),
    )
    db.add(config)
    db.flush()  # get workspace_id before seeding
    seed_builtin_policies(db, workspace_id)
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
        notify_on_block=cfg.notify_on_block,
        notify_on_budget=cfg.notify_on_budget,
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
    import uuid
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

    return InstallStatusOut(
        installed=True,
        workspace_id=workspace_id,
        invite_code=config.invite_code,
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
    config = _get_or_create_config(db, workspace_id)
    if body.alert_channel is not None:
        config.alert_channel = body.alert_channel
    if body.notify_on_block is not None:
        config.notify_on_block = body.notify_on_block
    if body.notify_on_budget is not None:
        config.notify_on_budget = body.notify_on_budget
    config.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(config)
    return _config_to_out(config)


@router.delete("", status_code=204)
def delete_config(
    db: Session = Depends(get_db),
    workspace_id: str = Depends(get_workspace_id),
):
    """Uninstall Guard for the workspace — removes guard_config and all guard_member_config rows."""
    import uuid
    try:
        ws_uuid = uuid.UUID(workspace_id)
    except ValueError:
        return
    db.query(GuardConfig).filter(GuardConfig.workspace_id == ws_uuid).delete()
    db.query(GuardMemberConfig).filter(GuardMemberConfig.workspace_id == ws_uuid).delete()
    db.commit()
    log.info("guard.config_deleted", workspace_id=workspace_id)


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
        GuardPolicy.active == True,
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
