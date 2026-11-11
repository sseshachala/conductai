"""Periodic alert checks run by the worker (#2142, #2524 item 9).

* Gateway profile alerts are derived asynchronously from recent gateway audit
  rows, so nothing is added to the request path. Events per (profile, event)
  are counted over one window and dispatched once; ``dispatch_alert`` applies
  the per-channel threshold and dedupe.
* Audit feed: a collector transitioning to stale (``FEED_STALE_AFTER``) alerts
  once; recovery alerts once. Per-collector state is kept in the Redis hash
  ``audit_feed:alert_state:{workspace_id}``.

Not covered yet: ``gateway.admission_refused`` (the 429 returns before any
audit row or profile resolution, so there is nothing to derive it from) and
``audit_chain.verification_failed`` (no scheduled chain verification; #2524).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import structlog

from app.modules.guard.alert_dispatch import dispatch_alert
from app.modules.guard.notification_registry import ALERT_ACTION

log = structlog.get_logger(__name__)

GATEWAY_WINDOW_SECONDS = 60
CHECK_INTERVAL_SECONDS = 60
FEED_STATE_TTL_SECONDS = 30 * 24 * 3600

_STALE, _OK = "stale", "ok"


def _workspaces_with_channels(db, source_type: str) -> list:
    from app.modules.guard.models import GuardNotificationChannel as C

    rows = db.query(C.workspace_id).filter(
        C.action == ALERT_ACTION, C.source_type == source_type, C.enabled.is_(True),
    ).distinct().all()
    return [r[0] for r in rows]


# ── Gateway ─────────────────────────────────────────────────────────────────

def gateway_event_counts(db, workspace_id, since: datetime) -> dict[tuple[str, str], int]:
    """Count gateway failures per (profile_id, event_type) since ``since``.

    Classification from the audit row:
      rate-limit rule                  -> rate_limit_exceeded
      guard.budget_* rule              -> spend_cap_refused
      execution_status = timeout       -> upstream_timeout
      error with 'HTTP 5xx' summary    -> upstream_5xx (excluding conduct-side
                                          refusals such as missing credentials)
    Rows without a v2 profile id (legacy v1 traffic) are ignored.
    """
    from sqlalchemy import and_, case, func, or_

    from app.modules.guard.models import GuardAuditEvent as E

    profile = E.routing_meta["gateway_profile_id"].astext
    event = case(
        (E.rule_id == "rate-limit", "rate_limit_exceeded"),
        (E.rule_id.like("guard.budget\\_%", escape="\\"), "spend_cap_refused"),
        (E.execution_status == "timeout", "upstream_timeout"),
        (and_(
            E.execution_status == "error",
            E.result_summary.op("~")("^HTTP 5[0-9][0-9]"),
            or_(E.rule_id.is_(None), E.rule_id.notin_(("credential-missing", "upstream-url-rejected"))),
        ), "upstream_5xx"),
        else_=None,
    )
    rows = (
        db.query(profile, event, func.count())
        .filter(
            E.workspace_id == workspace_id,
            E.source == "gateway",
            E.ts >= since,
            profile.isnot(None),
        )
        .group_by(profile, event)
        .all()
    )
    return {(p, ev): int(n) for p, ev, n in rows if ev is not None}


def check_gateway_alerts(db, *, now: datetime | None = None, client=None) -> int:
    """One pass over every workspace that has gateway alert channels."""
    from app.modules.guard.notification_registry import get_event

    now = now or datetime.now(timezone.utc)
    since = now - timedelta(seconds=GATEWAY_WINDOW_SECONDS)
    sent = 0
    for ws in _workspaces_with_channels(db, "gateway"):
        try:
            counts = gateway_event_counts(db, ws, since)
        except Exception:
            log.exception("guard.alerts.gateway_scan_failed", workspace_id=str(ws))
            continue
        for (profile_id, event_type), n in counts.items():
            ev = get_event("gateway", event_type)
            rate = n * 60.0 / GATEWAY_WINDOW_SECONDS
            sent += dispatch_alert(
                db, ws, "gateway", event_type, source_id=profile_id,
                title=f"Gateway: {ev.label}" if ev else f"Gateway: {event_type}",
                message=f"{n} in the last {GATEWAY_WINDOW_SECONDS}s on profile {profile_id}",
                details={"count": n, "window_seconds": GATEWAY_WINDOW_SECONDS, "profile_id": profile_id},
                rate_per_min=rate, dedupe_token="", client=client,
            )
    return sent


# ── Audit feed ──────────────────────────────────────────────────────────────

def _state_key(workspace_id) -> str:
    return f"audit_feed:alert_state:{workspace_id}"


def check_feed_alerts(db, *, now: datetime | None = None, client=None) -> int:
    """Alert once when a collector turns stale and once when it recovers."""
    from app.modules.guard.audit_export import _status_redis, feed_status

    now = now or datetime.now(timezone.utc)
    sent = 0
    for ws in _workspaces_with_channels(db, "audit_feed"):
        try:
            r = client or _status_redis()
            status = feed_status(ws, now=now, client=r)
            if not status.get("available"):
                continue
            key = _state_key(ws)
            previous = r.hgetall(key) or {}
            for c in status["collectors"]:
                actor = c["actor_id"]
                current = _STALE if c["stale"] else _OK
                before = previous.get(actor, _OK)
                if current == before:
                    continue
                # Persist first: at-most-once beats repeat spam if delivery hiccups.
                r.hset(key, actor, current)
                r.expire(key, FEED_STATE_TTL_SECONDS)
                if current == _STALE:
                    title = "Audit feed collector stale"
                    msg = (f"Collector {actor} has not pulled since {c['last_pull_at']} "
                           f"(threshold {status['stale_after_seconds'] // 60} min).")
                else:
                    title = "Audit feed collector recovered"
                    msg = f"Collector {actor} is pulling again (last pull {c['last_pull_at']})."
                sent += dispatch_alert(
                    db, ws, "audit_feed", "collector_stale", title=title, message=msg,
                    details={"collector": actor, "state": current, "last_pull_at": c["last_pull_at"]},
                    dedupe_token=current, client=client,
                )
        except Exception:
            log.exception("guard.alerts.feed_check_failed", workspace_id=str(ws))
    return sent


# ── Loop ────────────────────────────────────────────────────────────────────

def alert_checks_loop() -> None:
    """Daemon loop for the worker process."""
    from app.core.database import SessionLocal

    log.info("guard.alerts.worker_started", interval_seconds=CHECK_INTERVAL_SECONDS)
    while True:
        time.sleep(CHECK_INTERVAL_SECONDS)
        for check in (check_gateway_alerts, check_feed_alerts):
            try:
                with SessionLocal() as db:
                    check(db)
            except Exception:
                log.exception("guard.alerts.worker_error", check=check.__name__)
