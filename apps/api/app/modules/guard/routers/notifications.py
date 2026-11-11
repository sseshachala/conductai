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


def post_webhook(url: str, payload: dict, *, timeout: float = 10.0, signing_secret: str | None = None):
    """POST a JSON payload to an admin-configured webhook URL.

    With ``signing_secret`` the raw body is signed and sent as
    ``X-Conduct-Signature: t=<ts>,v1=<hex HMAC-SHA256 of "<ts>.<body>">``.

    The URL is checked with ``validate_outbound_url`` on every send (DNS may
    have changed since the channel was saved) and redirects are never
    followed, so a 3xx cannot point the request at an address the check did
    not see. Raises ``EgressBlocked`` when the URL is refused.
    """
    import httpx
    from app.core.egress import validate_outbound_url

    validate_outbound_url(url)
    if not signing_secret:
        return httpx.post(url, json=payload, timeout=timeout, follow_redirects=False)
    from app.modules.guard.channel_creds import SIGNATURE_HEADER, json_body, sign_webhook_body

    body = json_body(payload)
    return httpx.post(
        url,
        content=body,
        headers={"Content-Type": "application/json", SIGNATURE_HEADER: sign_webhook_body(signing_secret, body)},
        timeout=timeout,
        follow_redirects=False,
    )


def _check_webhook_ref(channel_type: str, ref: str) -> None:
    """Refuse webhook URLs that are not public https at save time (422)."""
    if channel_type != "webhook":
        return
    from app.core.egress import EgressBlocked, validate_outbound_url

    try:
        validate_outbound_url(ref, allow_unresolvable=True)
    except EgressBlocked as exc:
        raise HTTPException(status_code=422, detail=f"webhook URL refused: {exc}")

router = APIRouter(prefix="/guard/notifications", tags=["guard-notifications"])


ACTIONS = ("block", "warn", "audit", "approval", "fail_open", "drift")
CHANNEL_TYPES = ("slack", "email", "pagerduty", "webhook")


# ── Pydantic ──────────────────────────────────────────────────────────────────

class ChannelOut(BaseModel):
    id: str
    action: str
    channel_type: str
    integration_id: str | None
    channel_ref: str  # masked for legacy raw refs; a non-secret label for Vault-backed rows
    vault_handle: str | None = None
    environment_id: str | None = None
    environment_name: str | None = None
    legacy_ref: bool = False
    enabled: bool
    dedupe_window_sec: int
    created_at: datetime

    class Config:
        from_attributes = True


class ChannelCreate(BaseModel):
    action: Literal["block", "warn", "audit", "approval", "fail_open", "drift"]
    channel_type: Literal["slack", "webhook", "pagerduty", "email"] = "slack"
    integration_id: str | None = None
    # Slack channel / email recipient. For pagerduty/webhook pick a Vault entry
    # via integration_id; a raw ref is accepted only for legacy API clients.
    channel_ref: str = Field(default="", max_length=2048)
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

def _serialize(row: GuardNotificationChannel, info: dict | None = None) -> ChannelOut:
    from app.modules.guard.channel_creds import serialize_extras

    return ChannelOut(
        id=str(row.id),
        action=row.action,
        channel_type=row.channel_type,
        integration_id=str(row.integration_id) if row.integration_id else None,
        **serialize_extras(row, info or {}),
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
        .filter(
            GuardNotificationChannel.workspace_id == workspace_id,
            GuardNotificationChannel.source_type == "guard",
        )
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


def _serialize_one(db: Session, row: GuardNotificationChannel) -> ChannelOut:
    from app.modules.guard.channel_creds import vault_info

    return _serialize(row, vault_info(db, [row]))


def _rows_by_action(db: Session, workspace_id: _uuid.UUID) -> dict[str, list[GuardNotificationChannel]]:
    rows = (
        db.query(GuardNotificationChannel)
        .filter(
            GuardNotificationChannel.workspace_id == workspace_id,
            GuardNotificationChannel.source_type == "guard",
        )
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
            GuardNotificationChannel.source_type == "guard",
            GuardNotificationChannel.enabled.is_(True),
        )
        .all()
    )


def _pd_severity(action: str) -> str:
    """Map Guard action tier → PagerDuty severity."""
    return {
        "block": "error",
        "approval": "error",
        "warn": "warning",
        "audit": "info",
    }.get(action, "info")


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
    from app.modules.guard.channel_creds import vault_info

    grouped = _rows_by_action(db, ws)
    info = vault_info(db, [r for rows in grouped.values() for r in rows])
    return ListOut(
        workspace_id=workspace_id,
        groups=[
            ChannelsByAction(action=a, channels=[_serialize(r, info) for r in grouped.get(a, [])])
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

    from app.modules.guard.channel_creds import prepare_channel_ref

    ref = prepare_channel_ref(db, ws, body.channel_type, integration_uuid, body.channel_ref)

    row = GuardNotificationChannel(
        workspace_id=ws,
        action=body.action,
        channel_type=body.channel_type,
        integration_id=integration_uuid,
        channel_ref=ref,
        enabled=True,
        dedupe_window_sec=body.dedupe_window_sec,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log.info("guard.notifications.created", workspace_id=workspace_id, action=body.action,
             channel_type=body.channel_type)
    return _serialize_one(db, row)


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
    if body.integration_id is not None:
        try:
            row.integration_id = _uuid.UUID(body.integration_id) if body.integration_id else None
        except ValueError:
            raise HTTPException(status_code=400, detail="invalid integration_id")
    if body.channel_ref is not None or body.integration_id is not None:
        from app.modules.guard.channel_creds import prepare_channel_ref

        # Vault-backed pagerduty/webhook rows keep a label; a typed ref only
        # applies to slack/email or legacy (no Vault entry) rows.
        vault_backed = bool(row.integration_id) and row.channel_type in ("pagerduty", "webhook")
        if vault_backed:
            typed = ""
        elif body.channel_ref is not None:
            typed = body.channel_ref
        elif row.channel_type in ("pagerduty", "webhook") and row.channel_ref.startswith("vault:"):
            raise HTTPException(status_code=422, detail="provide channel_ref when unlinking the Vault entry")
        else:
            typed = row.channel_ref
        row.channel_ref = prepare_channel_ref(db, ws, row.channel_type, row.integration_id, typed)
    if body.dedupe_window_sec is not None:
        row.dedupe_window_sec = body.dedupe_window_sec
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _serialize_one(db, row)


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
    if row.channel_type == "pagerduty":
        from app.modules.guard.channel_creds import pagerduty_routing_key

        routing_key = pagerduty_routing_key(db, ws, row)
        if not routing_key:
            return TestResult(ok=False, error="No PagerDuty routing key: the Vault entry is missing or empty.")
        try:
            import httpx
            resp = httpx.post(
                "https://events.pagerduty.com/v2/enqueue",
                json={
                    "routing_key": routing_key,
                    "event_action": "trigger",
                    "payload": {
                        "summary": f"Guard notification test — action={row.action}",
                        "severity": _pd_severity(row.action),
                        "source": "conduct-guard",
                    },
                    "dedup_key": f"conduct-guard-test-{row.id}",
                },
                timeout=10.0,
            )
            if resp.status_code >= 400:
                return TestResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text[:200]}")
            return TestResult(ok=True)
        except Exception as e:
            log.warning("guard.notifications.pd_test_failed", err=str(e))
            return TestResult(ok=False, error=str(e)[:200])

    if row.channel_type == "email":
        try:
            from app.core.email import send_email
            ok = send_email(
                to=row.channel_ref,
                subject=f"Guard notification test — action={row.action}",
                html=f"<p>This is a synthetic Guard notification (workspace <code>{ws}</code>, action <code>{row.action}</code>).</p>",
                workspace_id=str(ws),
                db=db,
                integration_id=row.integration_id,
            )
            if not ok:
                return TestResult(ok=False, error="Email send failed — no Resend/SendGrid credential configured for this workspace or platform.")
            return TestResult(ok=True)
        except Exception as e:
            log.warning("guard.notifications.email_test_failed", err=str(e))
            return TestResult(ok=False, error=str(e)[:200])

    if row.channel_type == "webhook":
        try:
            payload = {
                "event": "guard.notification.test",
                "action": row.action,
                "rule_id": "test",
                "message": "synthetic notification from Guard settings",
            }
            from app.modules.guard.channel_creds import webhook_target

            url, secret = webhook_target(db, ws, row)
            if not url:
                return TestResult(ok=False, error="No webhook URL: the Vault entry is missing or empty.")
            resp = post_webhook(url, payload, signing_secret=secret)
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
