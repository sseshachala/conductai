"""Unified alert routing (#2142, #2524).

One surface for every alertable source: Guard rules, gateway profiles, audit
feed, audit chain. Rows are stored in ``guard_notification_channels`` (see
``app.modules.guard.notification_registry`` for the source/event model).

GET    /guard/alerts/registry       -- sources + event types (drives the UI)
GET    /guard/alerts                -- flat source -> event -> channels table
POST   /guard/alerts                -- add a channel to a non-guard source/event
PATCH  /guard/alerts/{id}           -- enable/disable, retarget, dedupe, threshold
DELETE /guard/alerts/{id}

Guard-rule rows keep being managed through /guard/notifications (unchanged);
they are listed here read-only so the table shows everything in one place.
Test sends reuse POST /guard/notifications/{id}/test.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.auth import get_workspace_id, require_permission
from app.core.database import get_db
from app.modules.guard.models import GuardNotificationChannel
from app.modules.guard.notification_registry import (
    ALERT_ACTION,
    GUARD_SOURCE,
    get_event,
    get_source,
    list_sources,
)
from app.modules.guard.routers.notifications import _check_webhook_ref

log = structlog.get_logger(__name__)

router = APIRouter(prefix="/guard/alerts", tags=["guard-alerts"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class EventOut(BaseModel):
    event_type: str
    label: str
    description: str
    severity: str
    supports_threshold: bool
    default_dedupe_sec: int


class SourceOut(BaseModel):
    source_type: str
    label: str
    scoped: bool
    events: list[EventOut]


class RegistryOut(BaseModel):
    sources: list[SourceOut]


class AlertChannelOut(BaseModel):
    id: str
    source_type: str
    source_id: str | None
    event_type: str
    channel_type: str
    integration_id: str | None
    channel_ref: str
    enabled: bool
    dedupe_window_sec: int
    threshold_per_min: int | None
    created_at: datetime
    # Guard rows are managed on /guard/notifications; the UI treats them as
    # read-only here.
    managed_elsewhere: bool = False


class AlertsOut(BaseModel):
    workspace_id: str
    channels: list[AlertChannelOut]


class AlertCreate(BaseModel):
    source_type: str = Field(..., min_length=1, max_length=32)
    source_id: str | None = Field(default=None, max_length=64)
    event_type: str = Field(..., min_length=1, max_length=48)
    channel_type: Literal["slack", "webhook", "pagerduty", "email"] = "slack"
    integration_id: str | None = None
    channel_ref: str = Field(..., min_length=1, max_length=2048)
    dedupe_window_sec: int | None = Field(default=None, ge=0, le=86400)
    threshold_per_min: int | None = Field(default=None, ge=1, le=100000)


class AlertPatch(BaseModel):
    enabled: bool | None = None
    channel_ref: str | None = Field(default=None, min_length=1, max_length=2048)
    integration_id: str | None = None
    dedupe_window_sec: int | None = Field(default=None, ge=0, le=86400)
    threshold_per_min: int | None = Field(default=None, ge=1, le=100000)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _ws_uuid(workspace_id: str) -> _uuid.UUID:
    try:
        return _uuid.UUID(workspace_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid workspace_id")


def _serialize(row: GuardNotificationChannel) -> AlertChannelOut:
    is_guard = (row.source_type or GUARD_SOURCE) == GUARD_SOURCE
    return AlertChannelOut(
        id=str(row.id),
        source_type=row.source_type or GUARD_SOURCE,
        source_id=row.source_id,
        event_type=row.action if is_guard else (row.event_type or ""),
        channel_type=row.channel_type,
        integration_id=str(row.integration_id) if row.integration_id else None,
        channel_ref=row.channel_ref,
        enabled=row.enabled,
        dedupe_window_sec=row.dedupe_window_sec,
        threshold_per_min=row.threshold_per_min,
        created_at=row.created_at,
        managed_elsewhere=is_guard,
    )


def _validate_source_id(db: Session, ws: _uuid.UUID, source_type: str, source_id: str | None) -> None:
    """Scoped sources may target one instance; the instance must belong to this workspace."""
    src = get_source(source_type)
    if source_id is None:
        return
    if not src or not src.scoped:
        raise HTTPException(status_code=422, detail=f"source {source_type!r} does not take a source_id")
    if source_type == "gateway":
        from app.models.gateway_profile import GatewayProfile

        try:
            pid = _uuid.UUID(source_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid gateway profile id")
        exists = db.query(GatewayProfile.id).filter(
            GatewayProfile.id == pid,
            GatewayProfile.workspace_id == ws,
            GatewayProfile.deleted_at.is_(None),
        ).first()
        if not exists:
            raise HTTPException(status_code=404, detail="gateway profile not found")


def _get_alert_row(db: Session, alert_id: str, ws: _uuid.UUID) -> GuardNotificationChannel:
    try:
        row = db.query(GuardNotificationChannel).filter(
            GuardNotificationChannel.id == _uuid.UUID(alert_id),
            GuardNotificationChannel.workspace_id == ws,
            GuardNotificationChannel.source_type != GUARD_SOURCE,
        ).first()
    except ValueError:
        row = None
    if not row:
        raise HTTPException(status_code=404, detail="alert channel not found")
    return row


def _parse_integration(value: str | None) -> _uuid.UUID | None:
    if not value:
        return None
    try:
        return _uuid.UUID(value)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid integration_id")


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/registry", response_model=RegistryOut)
def get_registry(
    _: str = Depends(require_permission("guard.policies.view")),
) -> RegistryOut:
    return RegistryOut(sources=[
        SourceOut(
            source_type=s.source_type,
            label=s.label,
            scoped=s.scoped,
            events=[
                EventOut(
                    event_type=e.event_type, label=e.label, description=e.description,
                    severity=e.severity, supports_threshold=e.supports_threshold,
                    default_dedupe_sec=e.default_dedupe_sec,
                )
                for e in s.events
            ],
        )
        for s in list_sources()
    ])


@router.get("", response_model=AlertsOut)
def list_alerts(
    source_type: str | None = Query(default=None, max_length=32),
    source_id: str | None = Query(default=None, max_length=64),
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> AlertsOut:
    ws = _ws_uuid(workspace_id)
    q = db.query(GuardNotificationChannel).filter(GuardNotificationChannel.workspace_id == ws)
    if source_type:
        q = q.filter(GuardNotificationChannel.source_type == source_type)
    if source_id:
        # A profile-filtered view also shows rows that cover every profile.
        q = q.filter(
            (GuardNotificationChannel.source_id == source_id)
            | (GuardNotificationChannel.source_id.is_(None))
        )
    rows = q.order_by(GuardNotificationChannel.created_at.asc()).all()
    return AlertsOut(workspace_id=workspace_id, channels=[_serialize(r) for r in rows])


@router.post("", response_model=AlertChannelOut, status_code=201)
def create_alert(
    body: AlertCreate,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> AlertChannelOut:
    ws = _ws_uuid(workspace_id)
    if body.source_type == GUARD_SOURCE:
        raise HTTPException(status_code=422, detail="guard rules are managed via /guard/notifications")
    event = get_event(body.source_type, body.event_type)
    if event is None:
        raise HTTPException(status_code=422, detail="unknown source_type / event_type")
    if body.threshold_per_min is not None and not event.supports_threshold:
        raise HTTPException(status_code=422, detail="this event does not support a threshold")
    _validate_source_id(db, ws, body.source_type, body.source_id)
    ref = body.channel_ref.strip()
    _check_webhook_ref(body.channel_type, ref)

    row = GuardNotificationChannel(
        workspace_id=ws,
        action=ALERT_ACTION,
        source_type=body.source_type,
        source_id=body.source_id,
        event_type=body.event_type,
        channel_type=body.channel_type,
        integration_id=_parse_integration(body.integration_id),
        channel_ref=ref,
        enabled=True,
        dedupe_window_sec=(
            body.dedupe_window_sec if body.dedupe_window_sec is not None else event.default_dedupe_sec
        ),
        threshold_per_min=body.threshold_per_min,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    log.info("guard.alerts.created", workspace_id=workspace_id,
             source_type=body.source_type, event_type=body.event_type,
             channel_type=body.channel_type)
    return _serialize(row)


@router.patch("/{alert_id}", response_model=AlertChannelOut)
def update_alert(
    alert_id: str,
    body: AlertPatch,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> AlertChannelOut:
    ws = _ws_uuid(workspace_id)
    row = _get_alert_row(db, alert_id, ws)
    if body.enabled is not None:
        row.enabled = body.enabled
    if body.channel_ref is not None:
        ref = body.channel_ref.strip()
        _check_webhook_ref(row.channel_type, ref)
        row.channel_ref = ref
    if body.integration_id is not None:
        row.integration_id = _parse_integration(body.integration_id)
    if body.dedupe_window_sec is not None:
        row.dedupe_window_sec = body.dedupe_window_sec
    if body.threshold_per_min is not None:
        event = get_event(row.source_type, row.event_type or "")
        if event is None or not event.supports_threshold:
            raise HTTPException(status_code=422, detail="this event does not support a threshold")
        row.threshold_per_min = body.threshold_per_min
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _serialize(row)


@router.delete("/{alert_id}")
def delete_alert(
    alert_id: str,
    workspace_id: str = Depends(get_workspace_id),
    db: Session = Depends(get_db),
    _: str = Depends(require_permission("guard.settings.edit")),
) -> dict:
    ws = _ws_uuid(workspace_id)
    row = _get_alert_row(db, alert_id, ws)
    db.delete(row)
    db.commit()
    log.info("guard.alerts.deleted", workspace_id=workspace_id,
             source_type=row.source_type, event_type=row.event_type)
    return {"deleted": alert_id}
