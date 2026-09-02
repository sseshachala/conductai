"""Customer-facing WARNING alert when Guard falls open (#1520 PR 2).

Companion to the internal ERROR alert in ``fail_open_alert.py``:

- Internal alert  → Conduct ops, `CONDUCT_INTERNAL_ALERT_SLACK_WEBHOOK`, per-surface
- Customer alert  → workspace's own `GuardConfig.slack_webhook_url`, per-workspace

The customer post is intentionally quieter than the internal one — 15-min
aggregate window, no error class or trace_id, no per-surface split. The
audience can't act on which surface failed; they need to know their rules
were not enforced and where to change the fail-mode.

Skipped when:
  - `GuardConfig.notify_on_fail_open` is False (customer opt-out)
  - `GuardConfig.slack_webhook_url` is empty (no channel configured)
  - the config row itself is missing
  - inside the 15-min rate-limit window
"""
from __future__ import annotations

import os
import time
import uuid

import httpx
import structlog
from sqlalchemy.orm import Session

from app.modules.guard.observability.name_cache import resolve_workspace_context

log = structlog.get_logger(__name__)

_RATE_LIMIT_SEC = 900  # 15 minutes per workspace
_HTTP_TIMEOUT_SEC = 3.0

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


def _build_message(*, workspace_name: str, count: int) -> dict:
    settings_url = f"{_settings_base_url()}/theguard/settings"
    events_line = (
        f"*{count} requests* in the last 15 min"
        if count > 1
        else "*1 request* just now"
    )
    return {
        "text": (
            f":warning: *Guard could not evaluate policy* on {events_line} in *{workspace_name}*.\n"
            f"Per your fail-open default, these requests were allowed through. "
            f"Guard rules were not enforced for the affected calls.\n"
            f"To change this behavior, set your workspace to fail-closed in "
            f"<{settings_url}|Guard Settings>."
        ),
    }


def _load_config(db: Session, workspace_id: str):
    """Load GuardConfig with only the fields we need. Returns None on any
    failure so the alert path never raises from the customer branch."""
    from sqlalchemy import text
    try:
        row = db.execute(
            text(
                "SELECT notify_on_fail_open, slack_webhook_url "
                "FROM guard_config WHERE workspace_id = :ws"
            ),
            {"ws": workspace_id},
        ).fetchone()
    except Exception as exc:  # noqa: BLE001
        log.warning("guard.fail_open.customer_config_lookup_failed", err=str(exc))
        return None
    return row


def notify_customer_fail_open(
    db: Session | None,
    *,
    workspace_id: str | uuid.UUID,
) -> None:
    """Best-effort customer WARNING post. Never raises.

    Rate-limited per workspace (not per surface) — the customer sees one
    channel, one message, aggregated.
    """
    if db is None:
        return

    ws_id = str(workspace_id)

    cfg = _load_config(db, ws_id)
    if cfg is None:
        return
    if not getattr(cfg, "notify_on_fail_open", True):
        return
    webhook = (getattr(cfg, "slack_webhook_url", None) or "").strip()
    if not webhook:
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

    payload = _build_message(workspace_name=workspace_name, count=count)

    try:
        httpx.post(webhook, json=payload, timeout=_HTTP_TIMEOUT_SEC)
    except Exception as exc:  # noqa: BLE001
        log.warning("guard.fail_open.customer_slack_post_failed", err=str(exc))


def _reset_dedup_for_tests() -> None:
    _dedup.clear()
