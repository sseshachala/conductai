"""Fan-out for non-guard alert sources (#2142, #2524).

``dispatch_alert`` finds the enabled channels registered for
(workspace, source_type, event_type[, source_id]) and delivers one message to
each, after applying two storm guards:

* per-channel threshold: skipped unless ``rate_per_min >= threshold_per_min``;
* per-channel dedupe: at most one delivery per ``dedupe_window_sec`` for the
  same (channel, source_id, event_type, dedupe_token). Window 0 disables it.

All transports go through the existing ``events_notify`` helpers, so webhook
URLs keep being validated by ``post_webhook`` / ``validate_outbound_url`` and
one failing channel never blocks the rest. Never raises.
"""
from __future__ import annotations

import time
import uuid as _uuid

import structlog

from app.modules.guard.notification_registry import ALERT_ACTION, get_event

log = structlog.get_logger(__name__)

# severity -> the Guard action tier the existing PagerDuty/Slack helpers know.
_SEVERITY_TIER = {"info": "audit", "warning": "warn", "error": "block", "critical": "block"}
_SEVERITY_ICON = {"info": "ℹ️", "warning": "⚠️", "error": "🚨", "critical": "🚨"}

# In-process fallback when Redis is unavailable, so an outage cannot turn a
# storm into one message per event. Cleared of expired keys on each use.
_local_seen: dict[str, float] = {}


def _redis():
    import redis

    from app.core.config import settings
    return redis.from_url(settings.redis_url, decode_responses=True, socket_timeout=2,
                          socket_connect_timeout=2)


def _claim(key: str, window_sec: int, client=None) -> bool:
    """True if this caller may send (first within the window)."""
    if window_sec <= 0:
        return True
    try:
        r = client or _redis()
        return bool(r.set(key, "1", nx=True, ex=window_sec))
    except Exception:
        now = time.monotonic()
        for k, exp in list(_local_seen.items()):
            if exp <= now:
                _local_seen.pop(k, None)
        if key in _local_seen:
            return False
        _local_seen[key] = now + window_sec
        return True


def _matching_channels(db, ws, source_type: str, event_type: str, source_id: str | None):
    from sqlalchemy import or_

    from app.modules.guard.models import GuardNotificationChannel as C

    q = db.query(C).filter(
        C.workspace_id == ws,
        C.action == ALERT_ACTION,
        C.source_type == source_type,
        C.event_type == event_type,
        C.enabled.is_(True),
    )
    if source_id is not None:
        q = q.filter(or_(C.source_id == source_id, C.source_id.is_(None)))
    else:
        q = q.filter(C.source_id.is_(None))
    return q.all()


def dispatch_alert(
    db,
    workspace_id,
    source_type: str,
    event_type: str,
    *,
    title: str,
    message: str,
    source_id: str | None = None,
    details: dict | None = None,
    rate_per_min: float | None = None,
    dedupe_token: str = "",
    client=None,
) -> int:
    """Deliver an alert to every eligible channel. Returns channels delivered to."""
    try:
        ws = workspace_id if isinstance(workspace_id, _uuid.UUID) else _uuid.UUID(str(workspace_id))
        event = get_event(source_type, event_type)
        if event is None:
            log.warning("guard.alerts.unknown_event", source_type=source_type, event_type=event_type)
            return 0
        eligible = []
        for ch in _matching_channels(db, ws, source_type, event_type, source_id):
            thr = ch.threshold_per_min
            if thr and (rate_per_min is None or rate_per_min < thr):
                continue
            key = f"alert_dedupe:{ch.id}:{source_id or '-'}:{event_type}:{dedupe_token}"
            if not _claim(key, ch.dedupe_window_sec or 0, client):
                continue
            eligible.append(ch)
        if not eligible:
            return 0

        from app.modules.guard.routers import events_notify as en

        tier = _SEVERITY_TIER.get(event.severity, "warn")
        icon = _SEVERITY_ICON.get(event.severity, "")
        text = f"{icon} *{title}*\n{message}"
        by_type: dict[str, list] = {}
        for ch in eligible:
            by_type.setdefault(ch.channel_type, []).append(ch)
        if by_type.get("slack"):
            en._fanout_slack(db, ws, by_type["slack"], text)
        if by_type.get("webhook"):
            en._fanout_webhook(by_type["webhook"], {
                "event": f"{source_type}.{event_type}",
                "severity": event.severity,
                "workspace_id": str(ws),
                "source_type": source_type,
                "source_id": source_id,
                "title": title,
                "message": message,
                "details": details or {},
            })
        if by_type.get("pagerduty"):
            en._fanout_pagerduty(by_type["pagerduty"], tier,
                                 f"{source_type}.{event_type}:{source_id or '-'}", f"{title}: {message}")
        if by_type.get("email"):
            en._fanout_email(db, ws, by_type["email"], subject=f"[Conduct] {title}",
                             html=f"<p><strong>{_esc(title)}</strong></p><p>{_esc(message)}</p>")
        log.info("guard.alerts.dispatched", workspace_id=str(ws), source_type=source_type,
                 event_type=event_type, channels=len(eligible))
        return len(eligible)
    except Exception:
        log.exception("guard.alerts.dispatch_failed", source_type=source_type, event_type=event_type)
        return 0


def _esc(s: str) -> str:
    import html
    return html.escape(s or "")
