"""Customer-facing WARNING alert when Guard falls open (#1520 PR 2 + PR 3).

Companion to the internal ERROR alert in ``fail_open_alert.py``:

- Internal alert  → Conduct ops, `CONDUCT_INTERNAL_ALERT_SLACK_WEBHOOK`, per-surface
- Customer alert  → workspace's own Slack, routed through the
  ``guard_notification_channels`` table under action="fail_open"

The customer post is intentionally quieter than the internal one — 15-min
aggregate window, no error class or trace_id, no per-surface split. The
audience can't act on which surface failed; they need to know their rules
were not enforced and where to change the fail-mode.

Skipped when:
  - ``GuardConfig.notify_on_fail_open`` is False (customer opt-out)
  - no ``fail_open`` channels configured in the "Slack channels by action" UI
  - inside the 15-min rate-limit window
"""
from __future__ import annotations

import os
import time
import uuid

import structlog
from sqlalchemy.orm import Session

from app.modules.guard.observability.name_cache import resolve_workspace_context

log = structlog.get_logger(__name__)

_RATE_LIMIT_SEC = 900  # 15 minutes per workspace

# (workspace_id,) -> (window_start_monotonic, event_count_in_window)
_dedup: dict[str, tuple[float, int]] = {}


def _now() -> float:
    return time.monotonic()


def _settings_base_url() -> str:
    return (os.environ.get("CONDUCT_WEB_URL") or "https://conductai.ai").rstrip("/")


def _should_post(workspace_id: str) -> tuple[bool, int]:
    """Return (post_now, count_in_prior_window).

    First hit posts immediately with count=1. Subsequent hits inside the
    15-min window silently increment. First hit after the window closes
    posts again, carrying the accumulated count so the customer sees
    magnitude.
    """
    now = _now()
    prior = _dedup.get(workspace_id)
    if prior is None:
        _dedup[workspace_id] = (now, 1)
        return True, 1

    window_start, count = prior
    if now - window_start < _RATE_LIMIT_SEC:
        _dedup[workspace_id] = (window_start, count + 1)
        return False, count + 1

    _dedup[workspace_id] = (now, 1)
    return True, count  # carry the prior window's count in the message


def _build_message(*, workspace_name: str, count: int) -> str:
    settings_url = f"{_settings_base_url()}/theguard/settings"
    events_line = (
        f"*{count} requests* in the last 15 min"
        if count > 1
        else "*1 request* just now"
    )
    return (
        f":warning: *Guard could not evaluate policy* on {events_line} in *{workspace_name}*.\n"
        f"Per your fail-open default, these requests were allowed through. "
        f"Guard rules were not enforced for the affected calls.\n"
        f"To change this behavior, set your workspace to fail-closed in "
        f"<{settings_url}|Guard Settings>."
    )


def _notify_on_fail_open_enabled(db: Session, workspace_id: str) -> bool:
    """Read the per-workspace opt-out flag. Defaults to True so a config
    lookup failure never silences transparency."""
    from sqlalchemy import text
    try:
        row = db.execute(
            text("SELECT notify_on_fail_open FROM guard_config WHERE workspace_id = :ws"),
            {"ws": workspace_id},
        ).fetchone()
    except Exception as exc:  # noqa: BLE001
        log.warning("guard.fail_open.customer_config_lookup_failed", err=str(exc))
        return True  # fail-open on the opt-out check itself
    if row is None:
        return True
    return bool(getattr(row, "notify_on_fail_open", True))


def notify_customer_fail_open(
    db: Session | None,
    *,
    workspace_id: str | uuid.UUID,
) -> None:
    """Best-effort customer WARNING post. Never raises.

    Rate-limited per workspace (not per surface) — the customer sees one
    channel, one message, aggregated. Routes through the per-action Slack
    fanout the workspace already configures for block/warn/audit/approval.
    """
    if db is None:
        return

    ws_id = str(workspace_id)

    if not _notify_on_fail_open_enabled(db, ws_id):
        return

    # Resolve channels via the same mechanism block/warn/audit/approval use.
    # If nothing is configured for `fail_open`, silently skip — customers
    # opt in by adding a channel in "Slack channels by action".
    try:
        from app.modules.guard.routers.notifications import resolve_channels
        channels = resolve_channels(db, ws_id, "fail_open")
    except Exception as exc:  # noqa: BLE001
        log.warning("guard.fail_open.customer_resolve_channels_failed", err=str(exc))
        return
    if not channels:
        return

    post_now, count = _should_post(ws_id)
    if not post_now:
        return

    try:
        ctx = resolve_workspace_context(db, ws_id)
        workspace_name = ctx.workspace_name
    except Exception as exc:  # noqa: BLE001
        log.warning("guard.fail_open.customer_context_failed", err=str(exc))
        workspace_name = ws_id

    text_msg = _build_message(workspace_name=workspace_name, count=count)

    try:
        from app.modules.guard.routers.events import _fanout_slack
        _fanout_slack(db, ws_id, channels, text_msg)
    except Exception as exc:  # noqa: BLE001
        log.warning("guard.fail_open.customer_fanout_failed", err=str(exc))


def _reset_dedup_for_tests() -> None:
    _dedup.clear()
