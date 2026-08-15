"""Guard notification channels (#1142 Phase 1).

Per-action-tier notification routing. Backs the /theguard/settings > Notifications
section. One row per (workspace, action, channel_type, channel_ref).

GET    /guard/notifications?workspace_id       — list, grouped by action (auto-seeds from legacy)
POST   /guard/notifications                    — create channel
PATCH  /guard/notifications/{id}               — toggle enabled / update fields
DELETE /guard/notifications/{id}
POST   /guard/notifications/{id}/test          — send synthetic Slack message

Resolver:
    resolve_channels(db, workspace_id, action) -> list[GuardNotificationChannel]
    used by events.py to fan out block/warn/audit/approval events to all enabled
    channels for that action tier.

Auto-seed: on first GET after migration, if the workspace has a legacy
guard_config.alert_channel and no rows in this table yet, seed one 'block' row
and one 'warn' row so the user's existing setup carries over.

Phase 2 (#1142) extends channel_type to email/pagerduty/webhook. Phase 3 adds
per-pack and per-rule overrides on top of this workspace-level table.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import require_permission
from app.core.database import get_db
from app.modules.guard.models import GuardConfig, GuardNotificationChannel

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/guard/notifications", tags=["guard-notifications"])


ACTIONS = ("block", "warn", "audit", "approval")
CHANNEL_TYPES = ("slack", "email", "pagerduty", "webhook")


# ── Pydantic ──────────────────────────────────────────────────────────────────

class ChannelOut(BaseModel):
    id: str
    action: str
    channel_type: str
    integration_id: str | None
    channel_ref: str
    enabled: bool
    dedupe_window_sec: int
    created_at: datetime

    class Config:
        from_attributes = True


class ChannelCreate(BaseModel):
    action: Literal["block", "warn", "audit", "approval"]
    channel_type: Literal["slack", "webhook"] = "slack"  # webhook added in Phase 2A
    integration_id: str | None = None
    channel_ref: str = Field(..., min_length=1, max_length=2048)
    dedupe_window_sec: int = Field(default=300, ge=0, le=86400)


class ChannelPatch(BaseModel):
    enabled: bool | None = None
    channel_ref: str | None = Field(default=None, min_length=1, max_length=2048)
    integration_id: str | None = None
    dedupe_window_sec: int | None = Field(default=None, ge=0, le=86400)


class ChannelsByAction(BaseModel):
    action: str
    channels: list[ChannelOut]


class ListOut(BaseModel):
    workspace_id: str
    groups: list[ChannelsByAction]


class TestResult(BaseModel):
    ok: bool
    error: str | None = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize(row: GuardNotificationChannel) -> ChannelOut:
    return ChannelOut(
        id=str(row.id),
        action=row.action,
        channel_type=row.channel_type,
        integration_id=str(row.integration_id) if row.integration_id else None,
        channel_ref=row.channel_ref,
        enabled=row.enabled,
        dedupe_window_sec=row.dedupe_window_sec,
        created_at=row.created_at,
    )


def _autoseed_from_legacy(db: Session, workspace_id: _uuid.UUID) -> None:
    """If no rows exist for this workspace and the legacy guard_config has an
    alert_channel + notify_on_block=True, materialize one 'block' row and one
    'warn' row so the user's setup carries over."""
    existing = (
        db.query(GuardNotificationChannel)
        .filter(GuardNotificationChannel.workspace_id == workspace_id)
        .first()
    )
    if existing:
        return
    cfg = db.query(GuardConfig).filter(GuardConfig.workspace_id == workspace_id).first()
    if not cfg or not cfg.alert_channel:
        return
    for action in ("block", "warn"):
        db.add(GuardNotificationChannel(
            workspace_id=workspace_id,
            action=action,
            channel_type="slack",
            integration_id=getattr(cfg, "alert_slack_integration_id", None),  # already a UUID from SQLAlchemy
            channel_ref=cfg.alert_channel,
            enabled=bool(cfg.notify_on_block),
        ))
    db.commit()
    log.info("guard.notifications.autoseeded", workspace_id=str(workspace_id))


def _rows_by_action(db: Session, workspace_id: _uuid.UUID) -> dict[str, list[GuardNotificationChannel]]:
    rows = (
        db.query(GuardNotificationChannel)
        .filter(GuardNotificationChannel.workspace_id == workspace_id)
        .order_by(GuardNotificationChannel.created_at.asc())
        .all()
    )
    out: dict[str, list[GuardNotificationChannel]] = {a: [] for a in ACTIONS}
    for r in rows:
        out.setdefault(r.action, []).append(r)
    return out


def _get_row(db: Session, notif_id: str, workspace_id: _uuid.UUID) -> GuardNotificationChannel:
    try:
        row = db.query(GuardNotificationChannel).filter(
            GuardNotificationChannel.id == _uuid.UUID(notif_id),
            GuardNotificationChannel.workspace_id == workspace_id,
        ).first()
    except ValueError:
        row = None
    if not row:
        raise HTTPException(status_code=404, detail="notification channel not found")
    return row


# ── Slack credential lookup (shared by fanout + test endpoint) ────────────

def slack_token_for_channel(db, workspace_id, integration_id, default_token: str = "") -> str:
    """Resolve the Slack bot token for one channel row.

    - If integration_id is set, decrypt that specific integration's cred blob.
    - Fall back to default_token (workspace-scoped lookup done once by the caller).
    Returns "" when nothing usable is available.
    """
    from app.core.crypto import decrypt
    from app.models.integration import Integration
    if integration_id:
        try:
            row = db.query(Integration).filter(Integration.id == integration_id).first()
            if row and row.encrypted_credentials:
                creds = decrypt(row.encrypted_credentials) or {}
                tok = creds.get("token") or creds.get("bot_token")
                if tok:
                    return tok
        except Exception:
            pass
    return default_token


# ── Public resolver (imported by events.py) ────────────────────────────────

def resolve_channels(
    db: Session, workspace_id: str | _uuid.UUID, action: str,
) -> list[GuardNotificationChannel]:
    """Return every enabled channel that should receive notifications for
    (workspace, action). Phase 1: workspace-level only. Phase 3 layers pack
    and rule overrides on top."""
    ws = workspace_id if isinstance(workspace_id, _uuid.UUID) else _uuid.UUID(str(workspace_id))
    return (
        db.query(GuardNotificationChannel)
        .filter(
            GuardNotificationChannel.workspace_id == ws,
            GuardNotificationChannel.action == action,
            GuardNotificationChannel.enabled.is_(True),
        )
        .all()
    )


# ── Endpoints ──────────────────────────────────────────────────────────────

@router.get("", response_model=ListOut)
def list_channels(
    workspace_id: str = Query(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> ListOut:
    try:
        ws = _uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid workspace_id")
    _autoseed_from_legacy(db, ws)
    grouped = _rows_by_action(db, ws)
    return ListOut(
        workspace_id=workspace_id,
        groups=[
            ChannelsByAction(action=a, channels=[_serialize(r) for r in grouped.get(a, [])])
            for a in ACTIONS
        ],
    )


@router.post("", response_model=ChannelOut, status_code=201)
def create_channel(
    body: ChannelCreate,
    workspace_id: str = Query(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> ChannelOut:
    try:
        ws = _uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid workspace_id")

    integration_uuid: _uuid.UUID | None = None
    if body.integration_id:
        try:
            integration_uuid = _uuid.UUID(body.integration_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid integration_id")

    row = GuardNotificationChannel(
        workspace_id=ws,
        action=body.action,
        channel_type=body.channel_type,
        integration_id=integration_uuid,
        channel_ref=body.channel_ref.strip(),
        enabled=True,
        dedupe_window_sec=body.dedupe_window_sec,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log.info("guard.notifications.created", workspace_id=workspace_id, action=body.action)
    return _serialize(row)


@router.patch("/{notif_id}", response_model=ChannelOut)
def update_channel(
    notif_id: str,
    body: ChannelPatch,
    workspace_id: str = Query(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> ChannelOut:
    try:
        ws = _uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid workspace_id")
    row = _get_row(db, notif_id, ws)
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.channel_ref is not None:
        row.channel_ref = body.channel_ref.strip()
    if body.integration_id is not None:
        try:
            row.integration_id = _uuid.UUID(body.integration_id) if body.integration_id else None
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid integration_id")
    if body.dedupe_window_sec is not None:
        row.dedupe_window_sec = body.dedupe_window_sec
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.delete("/{notif_id}")
def delete_channel(
    notif_id: str,
    workspace_id: str = Query(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> dict:
    try:
        ws = _uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid workspace_id")
    row = _get_row(db, notif_id, ws)
    db.delete(row)
    db.commit()
    return {"deleted": notif_id}


@router.post("/{notif_id}/test", response_model=TestResult)
def test_channel(
    notif_id: str,
    workspace_id: str = Query(...),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> TestResult:
    """Send a synthetic Slack message so the operator can verify the channel."""
    try:
        ws = _uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid workspace_id")
    row = _get_row(db, notif_id, ws)
    if row.channel_type == "webhook":
        try:
            import httpx, json as _json
            payload = {
                "event": "guard.notification.test",
                "action": row.action,
                "rule_id": "test",
                "message": "synthetic notification from Guard settings",
            }
            resp = httpx.post(row.channel_ref, json=payload, timeout=10.0)
            if resp.status_code >= 400:
                return TestResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}")
            return TestResult(ok=True)
        except Exception as e:
            log.warning("guard.notifications.webhook_test_failed", err=str(e))
            return TestResult(ok=False, error=str(e)[:200])

    if row.channel_type != "slack":
        return TestResult(ok=False, error=f"channel type {row.channel_type!r} not yet supported")

    try:
        from app.core.credentials import get_credential

        default = get_credential(db, str(ws), "slack") or {}
        default_token = default.get("token") or default.get("bot_token") or ""
        token = slack_token_for_channel(db, ws, row.integration_id, default_token)
        if not token:
            return TestResult(ok=False, error="No Slack credentials configured for this workspace or environment.")
        from app.runtime.integrations.slack import post_message
        post_message(
            token=token,
            channel=row.channel_ref,
            text=f":test_tube: Guard notification test — action=`{row.action}` — this is a synthetic event.",
        )
        return TestResult(ok=True)
    except Exception as e:
        log.warning("guard.notifications.test_failed", err=str(e))
        return TestResult(ok=False, error=str(e)[:200])
